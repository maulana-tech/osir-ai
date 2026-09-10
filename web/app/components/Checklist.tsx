"use client";

import Link from "next/link";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Checklist as ChecklistData } from "@/lib/types.admin";

const LINKS: Record<string, (ws: string) => string> = {
  connect_account: (ws) => `/w/${ws}/channels`,
  create_post: (ws) => `/workspace/${ws}/composer/new/`,
  schedule_post: (ws) => `/w/${ws}/calendar`,
  invite_member: () => "/org/members",
  set_timezone: (ws) => `/w/${ws}/settings`,
};

export function Checklist({ workspaceId, data }: { workspaceId: string; data: ChecklistData }) {
  const { run, busy } = useAction();
  return (
    <div className="panel mb-6 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm font-semibold">
          Getting started · {data.completed}/{data.total}
        </div>
        <button className="text-xs underline" style={{ color: "var(--muted)" }} disabled={busy} onClick={() => run(() => call(`/api/web/workspaces/${workspaceId}/checklist/dismiss`, { method: "POST" }))}>
          Dismiss
        </button>
      </div>
      <ul className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {data.items.map((i) => {
          const href = LINKS[i.key]?.(workspaceId);
          const inner = (
            <>
              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px]" style={{ borderColor: i.completed ? "#0a0a0a" : "var(--line)", background: i.completed ? "#0a0a0a" : "transparent", color: "#fff" }}>
                {i.completed ? "✓" : ""}
              </span>
              <span style={{ textDecoration: i.completed ? "line-through" : undefined, color: i.completed ? "var(--muted)" : undefined }}>{i.title}</span>
            </>
          );
          return (
            <li key={i.key} title={i.description}>
              {href && !i.completed ? (
                <Link href={href} className="flex items-center gap-2 hover:underline">
                  {inner}
                </Link>
              ) : (
                <span className="flex items-center gap-2">{inner}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
