"use client";

import { useState } from "react";
import { Empty, Section, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Members } from "@/lib/types.admin";

type Assignment = { workspace_id: string; role: string };

/** Per-workspace role picker; "—" means no access. */
function AssignmentEditor({
  workspaces,
  roles,
  value,
  onChange,
  disabled,
}: {
  workspaces: { id: string; name: string }[];
  roles: { value: string; label: string }[];
  value: Assignment[];
  onChange: (v: Assignment[]) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid gap-1 sm:grid-cols-2">
      {workspaces.map((w) => {
        const current = value.find((a) => a.workspace_id === w.id)?.role ?? "";
        return (
          <label key={w.id} className="flex items-center gap-2 text-xs">
            <span className="w-32 truncate" title={w.name}>
              {w.name}
            </span>
            <select
              className="input py-1"
              value={current}
              disabled={disabled}
              onChange={(e) => {
                const rest = value.filter((a) => a.workspace_id !== w.id);
                onChange(e.target.value ? [...rest, { workspace_id: w.id, role: e.target.value }] : rest);
              }}
            >
              <option value="">— no access</option>
              {roles.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
        );
      })}
    </div>
  );
}

function MemberRow({ m, data }: { m: Members["members"][number]; data: Members }) {
  const { run, busy, Feedback } = useAction();
  const [editing, setEditing] = useState(false);
  const [assign, setAssign] = useState<Assignment[]>(m.workspaces.map((w) => ({ workspace_id: w.id, role: w.role })));
  const self = m.user_id === data.current_user_id;
  const base = `/api/web/org/members/${m.membership_id}`;
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-semibold">
            {m.name} {self && <span className="pill">you</span>}
          </div>
          <div className="text-xs" style={{ color: "var(--muted)" }}>
            {m.email}
            {m.joined_at && ` · joined ${timeAgo(m.joined_at)}`}
            {!editing && m.workspaces.length > 0 && ` · ${m.workspaces.map((w) => `${w.name}: ${w.role}`).join(", ")}`}
          </div>
        </div>
        {data.is_admin && !self ? (
          <select className="input w-auto py-1" value={m.org_role} disabled={busy} onChange={(e) => run(() => call(`${base}/role`, { method: "POST", body: JSON.stringify({ org_role: e.target.value }) }), "Role updated")}>
            {data.org_role_choices.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        ) : (
          <span className="pill">{m.org_role}</span>
        )}
        {data.is_admin && (
          <button className="btn" onClick={() => setEditing((v) => !v)}>
            {editing ? "Close" : "Workspaces"}
          </button>
        )}
        {data.is_admin && !self && (
          <button className="btn btn-bad" disabled={busy} onClick={() => window.confirm(`Remove ${m.email} from the organization?`) && run(() => call(base, { method: "DELETE" }), "Removed")}>
            Remove
          </button>
        )}
      </div>
      {editing && (
        <div className="mt-3 rounded-lg border p-3" style={{ borderColor: "var(--line)" }}>
          <AssignmentEditor workspaces={data.workspaces} roles={data.workspace_role_choices} value={assign} onChange={setAssign} disabled={busy} />
          <div className="mt-2 flex justify-end">
            <button
              className="btn btn-accent"
              disabled={busy}
              onClick={async () => {
                const r = await run(() => call(`${base}/workspaces`, { method: "PUT", body: JSON.stringify({ workspaces: assign }) }), "Workspace access saved");
                if (r !== undefined) setEditing(false);
              }}
            >
              Save access
            </button>
          </div>
        </div>
      )}
      <Feedback />
    </li>
  );
}

export function MembersView({ data }: { data: Members }) {
  const invite = useAction();
  const pending = useAction();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(data.org_role_choices[0]?.value ?? "member");
  const [assign, setAssign] = useState<Assignment[]>([]);

  return (
    <div className="space-y-6">
      <Section title="Members" hint={`${data.members.length}`}>
        <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
          {data.members.map((m) => (
            <MemberRow key={m.membership_id} m={m} data={data} />
          ))}
        </ul>
      </Section>

      {data.pending_invites.length > 0 && (
        <Section title="Pending invitations" hint={`${data.pending_invites.length}`}>
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {data.pending_invites.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{i.email}</div>
                  <div className="text-xs" style={{ color: "var(--muted)" }}>
                    {i.org_role}
                    {i.invited_by && ` · invited by ${i.invited_by}`} · expires {new Date(i.expires_at).toLocaleDateString()}
                    {i.workspace_assignments.length > 0 && ` · ${i.workspace_assignments.map((a) => `${data.workspaces.find((w) => w.id === a.workspace_id)?.name ?? "?"}: ${a.role}`).join(", ")}`}
                  </div>
                </div>
                {data.is_admin && (
                  <>
                    <button className="btn" disabled={pending.busy} onClick={() => pending.run(() => call(`/api/web/org/members/invites/${i.id}/resend`, { method: "POST" }), "Invitation resent")}>
                      Resend
                    </button>
                    <button className="btn btn-bad" disabled={pending.busy} onClick={() => pending.run(() => call(`/api/web/org/members/invites/${i.id}`, { method: "DELETE" }), "Invitation revoked")}>
                      Revoke
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
          <pending.Feedback />
        </Section>
      )}

      {data.is_admin ? (
        <Section title="Invite a teammate">
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <input className="input flex-1" type="email" placeholder="teammate@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              <select className="input w-auto" value={role} onChange={(e) => setRole(e.target.value)}>
                {data.org_role_choices.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="mb-1 text-xs" style={{ color: "var(--muted)" }}>
                Workspace access
              </div>
              <AssignmentEditor workspaces={data.workspaces} roles={data.workspace_role_choices} value={assign} onChange={setAssign} />
            </div>
            <div className="flex justify-end">
              <button
                className="btn btn-accent"
                disabled={invite.busy || !email.trim()}
                onClick={() =>
                  invite.run(async () => {
                    await call("/api/web/org/members/invite", { method: "POST", body: JSON.stringify({ email, org_role: role, workspaces: assign }) });
                    setEmail("");
                    setAssign([]);
                  }, "Invitation sent")
                }
              >
                Send invitation
              </button>
            </div>
            <invite.Feedback />
          </div>
        </Section>
      ) : (
        data.members.length === 0 && <Empty>No members.</Empty>
      )}
    </div>
  );
}
