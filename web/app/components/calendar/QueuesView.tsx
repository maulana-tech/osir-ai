"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { QueuesData } from "@/lib/types.calendar";

export function QueuesView({ workspaceId, data }: { workspaceId: string; data: QueuesData }) {
  const { run, busy, Feedback } = useAction();
  const [name, setName] = useState("");
  const [account, setAccount] = useState(data.accounts[0]?.id ?? "");
  const [category, setCategory] = useState("");
  const base = `/api/web/workspaces/${workspaceId}/calendar/queues`;
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Section title="Queues" hint={`${data.queues.length}`}>
        <p className="mb-3 text-xs" style={{ color: "var(--muted)" }}>
          A queue fills a channel&apos;s posting slots in order. From the composer, “Next available slot” drops a post into the queue for each selected channel.
        </p>
        {data.queues.length === 0 ? (
          <Empty>No queues yet.</Empty>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {data.queues.map((q) => (
              <li key={q.id} className="flex items-center gap-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <Link href={`/w/${workspaceId}/calendar/queues/${q.id}`} className="font-semibold hover:underline">
                    {q.name}
                  </Link>
                  <div className="text-xs" style={{ color: "var(--muted)" }}>
                    {q.account.name} · {q.account.platform.replace("_", " ")}
                    {q.category && ` · ${q.category.name}`} · {q.entry_count} queued
                  </div>
                </div>
                <button className="btn btn-bad" disabled={busy} onClick={() => window.confirm(`Delete queue "${q.name}"? Queued posts keep their scheduled times.`) && run(() => call(`${base}/${q.id}`, { method: "DELETE" }), "Deleted")}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
        <Feedback />
      </Section>
      <Section title="New queue">
        {data.accounts.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Connect a channel first.
          </p>
        ) : (
          <div className="space-y-2 text-sm">
            <input className="input" placeholder="Queue name" value={name} onChange={(e) => setName(e.target.value)} />
            <select className="input" value={account} onChange={(e) => setAccount(e.target.value)}>
              {data.accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.platform})
                </option>
              ))}
            </select>
            <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Any category</option>
              {data.categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <div className="flex justify-end">
              <button
                className="btn btn-accent"
                disabled={busy || !name.trim() || !account}
                onClick={async () => {
                  const r = await run(() => call(base, { method: "POST", body: JSON.stringify({ name, social_account_id: account, category_id: category || null }) }), "Created");
                  if (r !== undefined) setName("");
                }}
              >
                Create
              </button>
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}
