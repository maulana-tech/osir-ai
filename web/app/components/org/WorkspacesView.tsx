"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Empty, Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { OrgWorkspaces } from "@/lib/types.admin";

export function WorkspacesView({ data }: { data: OrgWorkspaces }) {
  const router = useRouter();
  const { run, busy, Feedback } = useAction();
  const [name, setName] = useState("");
  return (
    <div className="space-y-6">
      <Section title="All workspaces" hint={`${data.workspaces.length}`}>
        {data.workspaces.length === 0 ? (
          <Empty>No workspaces yet.</Empty>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {data.workspaces.map((w) => (
              <li key={w.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {w.is_member ? (
                      <Link href={`/w/${w.id}/calendar`} className="font-semibold hover:underline">
                        {w.name}
                      </Link>
                    ) : (
                      <span className="font-semibold">{w.name}</span>
                    )}
                    {w.is_archived && <span className="pill">archived</span>}
                    {!w.is_member && <span className="pill">not a member</span>}
                  </div>
                  <div className="truncate text-xs" style={{ color: "var(--muted)" }}>
                    {w.member_count} member{w.member_count === 1 ? "" : "s"}
                    {w.members.length > 0 && ` · ${w.members.map((m) => `${m.name} (${m.role})`).join(", ")}`}
                  </div>
                </div>
                {w.can_manage && (
                  <Link href={`/w/${w.id}/settings`} className="btn">
                    Settings
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {data.can_create && (
        <Section title="Create a workspace">
          <div className="flex gap-2">
            <input className="input" placeholder="Workspace name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
            <button
              className="btn btn-accent shrink-0"
              disabled={busy || !name.trim()}
              onClick={async () => {
                const r = await run(() => call<{ id: string }>("/api/web/org/workspaces", { method: "POST", body: JSON.stringify({ name }) }));
                if (r) router.push(`/w/${r.id}/channels`);
              }}
            >
              Create
            </button>
          </div>
          <Feedback />
        </Section>
      )}
    </div>
  );
}
