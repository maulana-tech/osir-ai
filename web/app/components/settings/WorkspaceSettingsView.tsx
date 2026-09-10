"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Empty, Section, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Clients, WorkspaceSettings } from "@/lib/types.admin";

const APPROVAL_COPY: Record<string, string> = {
  none: "Anyone with publishing rights can schedule or publish directly.",
  optional: "Creators can submit a post for review, but it's not required.",
  required_internal: "Every post must be approved by a team member with review rights before it can go out.",
  required_internal_and_client: "Posts go through internal review, then the client portal for final sign-off.",
};
const AUTONOMY_COPY: Record<string, string> = {
  off: "The agent only observes and reports. It changes nothing.",
  draft_only: "The agent replies to routine inbox items and creates drafts; every post goes through approval.",
  autopilot: "The agent may also schedule routine posts directly when the approval workflow allows it, and still escalates anything sensitive.",
};

export function WorkspaceSettingsView({ workspaceId, settings, clients }: { workspaceId: string; settings: WorkspaceSettings; clients: Clients | null }) {
  const router = useRouter();
  const base = `/api/web/workspaces/${workspaceId}/settings`;
  const general = useAction();
  const workflow = useAction();
  const danger = useAction();
  const clientAct = useAction();
  const [name, setName] = useState(settings.name);
  const [description, setDescription] = useState(settings.description);
  const [tz, setTz] = useState(settings.timezone);
  const [approval, setApproval] = useState(settings.approval_workflow_mode);
  const [autonomy, setAutonomy] = useState(settings.agent_autonomy);
  const [clientEmail, setClientEmail] = useState("");
  const ro = !settings.is_owner_or_manager;

  async function uploadIcon(file: File | null, remove = false) {
    const fd = new FormData();
    if (file) fd.append("icon", file);
    if (remove) fd.append("remove", "true");
    const csrf = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] ?? "";
    const res = await fetch(`${base}/icon`, { method: "POST", body: fd, headers: { "X-CSRFToken": decodeURIComponent(csrf) } });
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail ?? "Upload failed");
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="General">
        <div className="space-y-3 text-sm">
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Name
            </span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} disabled={ro} />
          </label>
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Description
            </span>
            <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} disabled={ro} maxLength={500} />
          </label>
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Timezone (blank = organization default, currently {settings.effective_timezone})
            </span>
            <select className="input" value={tz} onChange={(e) => setTz(e.target.value)} disabled={ro}>
              <option value="">Organization default</option>
              {settings.timezones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-3">
            {settings.icon_url ? <img src={settings.icon_url} alt="" className="h-10 w-10 rounded-lg object-cover" /> : <div className="h-10 w-10 rounded-lg border" style={{ borderColor: "var(--line)" }} />}
            {!ro && (
              <>
                <label className="btn cursor-pointer">
                  Upload logo
                  <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={(e) => e.target.files?.[0] && general.run(() => uploadIcon(e.target.files![0]), "Logo updated")} />
                </label>
                {settings.icon_url && (
                  <button className="btn" onClick={() => general.run(() => uploadIcon(null, true), "Logo removed")}>
                    Remove
                  </button>
                )}
              </>
            )}
          </div>
          {!ro && (
            <div className="flex justify-end">
              <button className="btn btn-accent" disabled={general.busy} onClick={() => general.run(() => call(base, { method: "PATCH", body: JSON.stringify({ name, description, timezone: tz }) }), "Saved")}>
                Save
              </button>
            </div>
          )}
          <general.Feedback />
        </div>
      </Section>

      <Section title="Approvals and autopilot">
        <div className="space-y-4 text-sm">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Approval workflow
            </div>
            <div className="space-y-1">
              {settings.approval_modes.map((m) => (
                <label key={m.value} className="flex cursor-pointer items-start gap-2 rounded-lg border p-2" style={{ borderColor: approval === m.value ? "#0a0a0a" : "var(--line)" }}>
                  <input type="radio" name="approval" value={m.value} checked={approval === m.value} onChange={() => setApproval(m.value)} disabled={ro} className="mt-1" />
                  <span>
                    <span className="font-semibold">{m.label}</span>
                    <span className="block text-xs" style={{ color: "var(--muted)" }}>
                      {APPROVAL_COPY[m.value]}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Osir AI autopilot
            </div>
            <div className="space-y-1">
              {settings.autonomy_levels.map((m) => (
                <label key={m.value} className="flex cursor-pointer items-start gap-2 rounded-lg border p-2" style={{ borderColor: autonomy === m.value ? "#0a0a0a" : "var(--line)" }}>
                  <input type="radio" name="autonomy" value={m.value} checked={autonomy === m.value} onChange={() => setAutonomy(m.value)} disabled={ro} className="mt-1" />
                  <span>
                    <span className="font-semibold">{m.label}</span>
                    <span className="block text-xs" style={{ color: "var(--muted)" }}>
                      {AUTONOMY_COPY[m.value]}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>
          {!ro && (
            <div className="flex justify-end">
              <button className="btn btn-accent" disabled={workflow.busy} onClick={() => workflow.run(() => call(base, { method: "PATCH", body: JSON.stringify({ approval_workflow_mode: approval, agent_autonomy: autonomy }) }), "Saved")}>
                Save
              </button>
            </div>
          )}
          <workflow.Feedback />
        </div>
      </Section>

      {clients && (
        <Section title="Client portal" hint={`${clients.clients.length} client${clients.clients.length === 1 ? "" : "s"}`}>
          <p className="mb-3 text-xs" style={{ color: "var(--muted)" }}>
            Clients sign in with a magic link and see only the approval queue, published posts, activity, and reports.
          </p>
          {clients.clients.length === 0 && clients.pending_invites.length === 0 && <Empty>No clients yet.</Empty>}
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {clients.clients.map((c) => (
              <li key={c.membership_id} className="flex items-center gap-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{c.name}</div>
                  <div className="text-xs" style={{ color: "var(--muted)" }}>
                    {c.email} · {c.link_expires_at ? `link valid until ${new Date(c.link_expires_at).toLocaleDateString()}` : "no active link"}
                    {c.link_last_used_at && ` · last used ${timeAgo(c.link_last_used_at)}`}
                  </div>
                </div>
                <button className="btn" disabled={clientAct.busy} onClick={() => clientAct.run(() => call(`/api/web/workspaces/${workspaceId}/clients/${c.membership_id}/send-link`, { method: "POST" }), "Link sent")}>
                  Send link
                </button>
                <button className="btn btn-bad" disabled={clientAct.busy} onClick={() => window.confirm(`Remove ${c.email}?`) && clientAct.run(() => call(`/api/web/workspaces/${workspaceId}/clients/${c.membership_id}`, { method: "DELETE" }), "Removed")}>
                  Remove
                </button>
              </li>
            ))}
            {clients.pending_invites.map((i) => (
              <li key={i.id} className="flex items-center gap-3 py-2 text-sm" style={{ color: "var(--muted)" }}>
                <span className="pill">invited</span>
                {i.email} · expires {new Date(i.expires_at).toLocaleDateString()}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex gap-2">
            <input className="input" type="email" placeholder="client@example.com" value={clientEmail} onChange={(e) => setClientEmail(e.target.value)} />
            <button
              className="btn btn-accent shrink-0"
              disabled={clientAct.busy || !clientEmail.trim()}
              onClick={() =>
                clientAct.run(async () => {
                  await call(`/api/web/workspaces/${workspaceId}/clients/invite`, { method: "POST", body: JSON.stringify({ email: clientEmail }) });
                  setClientEmail("");
                }, "Invitation sent")
              }
            >
              Invite client
            </button>
          </div>
          <clientAct.Feedback />
        </Section>
      )}

      {settings.is_owner_or_manager && (
        <Section title="Danger zone">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {settings.is_archived ? (
              <button className="btn" disabled={danger.busy} onClick={() => danger.run(() => call(`${base}/unarchive`, { method: "POST" }), "Restored")}>
                Restore workspace
              </button>
            ) : (
              <button className="btn" disabled={danger.busy || !settings.can_archive} title={settings.can_archive ? "" : "The last active workspace cannot be archived"} onClick={() => window.confirm("Archive this workspace? Members lose access until it is restored.") && danger.run(() => call(`${base}/archive`, { method: "POST" }), "Archived")}>
                Archive workspace
              </button>
            )}
            <button
              className="btn btn-bad"
              disabled={danger.busy || !settings.can_delete}
              title={settings.can_delete ? "" : "The last active workspace cannot be deleted"}
              onClick={async () => {
                if (!window.confirm(`Permanently delete "${settings.name}" and everything in it?`)) return;
                const ok = await danger.run(() => call(base, { method: "DELETE" }));
                if (ok !== undefined) router.push("/org/workspaces");
              }}
            >
              Delete workspace
            </button>
          </div>
          <danger.Feedback />
        </Section>
      )}
    </div>
  );
}
