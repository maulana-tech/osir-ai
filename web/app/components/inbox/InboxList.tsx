"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { timeAgo } from "@/app/components/ui";
import { call } from "@/lib/client";
import type { InboxFeed, InboxMessage } from "@/lib/types.inbox";

const TYPE_LABEL: Record<string, string> = { comment: "Comment", mention: "Mention", dm: "DM", review: "Review" };
const SENTIMENT_DOT: Record<string, string> = { positive: "#0a0a0a", neutral: "#a3a3a3", negative: "#dc2626" };

export function InboxList({
  workspaceId,
  feed,
  selectedId,
  query,
}: {
  workspaceId: string;
  feed: InboxFeed;
  selectedId: string | null;
  query: Record<string, string>;
}) {
  const router = useRouter();
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const base = `/w/${workspaceId}/inbox`;

  const withQuery = (patch: Record<string, string | undefined>) => {
    const p = new URLSearchParams(query);
    for (const [k, v] of Object.entries(patch)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    p.delete("offset");
    return `${base}?${p}`;
  };
  const selectHref = (m: InboxMessage) => {
    const p = new URLSearchParams(query);
    p.set("m", m.id);
    return `${base}?${p}`;
  };

  async function bulk(action: string, value = "") {
    if (checked.size === 0) return;
    setBusy(true);
    try {
      await call(`/api/web/workspaces/${workspaceId}/inbox/bulk`, {
        method: "POST",
        body: JSON.stringify({ message_ids: [...checked], action, value }),
      });
      setChecked(new Set());
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const view = query.view ?? "all";
  return (
    <div className="panel flex min-h-0 flex-col">
      <div className="space-y-2 border-b p-3" style={{ borderColor: "var(--line)" }}>
        <form action={base} className="flex gap-2">
          {Object.entries(query)
            .filter(([k]) => k !== "q" && k !== "offset")
            .map(([k, v]) => (
              <input key={k} type="hidden" name={k} value={v} />
            ))}
          <input name="q" defaultValue={query.q ?? ""} placeholder="Search sender or text" className="input" />
        </form>
        <div className="flex flex-wrap gap-1 text-xs">
          {(["all", "mine", "unassigned"] as const).map((v) => (
            <Link key={v} href={withQuery({ view: v === "all" ? undefined : v })} className="pill" style={view === v ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined}>
              {v}
            </Link>
          ))}
          <select className="input ml-auto w-auto" value={query.status ?? ""} onChange={(e) => router.push(withQuery({ status: e.target.value || undefined }))} aria-label="Status">
            <option value="">any status</option>
            {["unread", "open", "resolved", "archived"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select className="input w-auto" value={query.account ?? ""} onChange={(e) => router.push(withQuery({ account: e.target.value || undefined }))} aria-label="Channel">
            <option value="">all channels</option>
            {feed.accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <select className="input w-auto" value={query.sentiment ?? ""} onChange={(e) => router.push(withQuery({ sentiment: e.target.value || undefined }))} aria-label="Sentiment">
            <option value="">any mood</option>
            {["positive", "neutral", "negative"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        {feed.can_reply && checked.size > 0 && (
          <div className="flex flex-wrap items-center gap-1 text-xs">
            <span style={{ color: "var(--muted)" }}>{checked.size} selected:</span>
            <button className="btn" disabled={busy} onClick={() => bulk("mark_read")}>
              mark read
            </button>
            <button className="btn" disabled={busy} onClick={() => bulk("resolve")}>
              resolve
            </button>
            <button className="btn" disabled={busy} onClick={() => bulk("archive")}>
              archive
            </button>
            <select className="input w-auto" disabled={busy} defaultValue="" onChange={(e) => e.target.value && bulk("assign", e.target.value)} aria-label="Assign">
              <option value="">assign to…</option>
              {feed.team.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <ul className="min-h-0 flex-1 divide-y overflow-y-auto" style={{ borderColor: "var(--line)" }}>
        {feed.messages.length === 0 && (
          <li className="p-6 text-center text-sm" style={{ color: "var(--muted)" }}>
            No messages match.
          </li>
        )}
        {feed.messages.map((m) => {
          const active = m.id === selectedId;
          return (
            <li key={m.id} className="flex gap-2 px-3 py-2.5" style={{ background: active ? "#f5f5f5" : undefined }}>
              {feed.can_reply && (
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={checked.has(m.id)}
                  onChange={(e) => {
                    const next = new Set(checked);
                    if (e.target.checked) next.add(m.id);
                    else next.delete(m.id);
                    setChecked(next);
                  }}
                  aria-label={`Select message from ${m.sender_name}`}
                />
              )}
              <Link href={selectHref(m)} className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: SENTIMENT_DOT[m.sentiment] ?? "#e5e5e5" }} title={m.sentiment || "no sentiment"} />
                  <span className={m.status === "unread" ? "font-bold" : "font-semibold"}>{m.sender_name}</span>
                  <span style={{ color: "var(--muted)" }}>
                    {TYPE_LABEL[m.message_type]} · {m.account.name}
                  </span>
                  <span className="ml-auto" style={{ color: "var(--muted)" }}>
                    {timeAgo(m.received_at)}
                  </span>
                </div>
                <p className="mt-0.5 line-clamp-2 text-sm" style={{ color: m.status === "unread" ? "#0a0a0a" : "var(--muted)" }}>
                  {m.body}
                </p>
                <div className="mt-1 flex gap-2 text-[11px]" style={{ color: "var(--muted)" }}>
                  <span className="pill">{m.status}</span>
                  {m.assigned_to && <span>→ {m.assigned_to.name}</span>}
                  {m.reply_count > 0 && <span>{m.reply_count} replies</span>}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
      {feed.next_offset !== null && (
        <div className="border-t p-2 text-center text-xs" style={{ borderColor: "var(--line)" }}>
          <Link href={`${base}?${new URLSearchParams({ ...query, offset: String(feed.next_offset) })}`} className="hover:text-black" style={{ color: "var(--muted)" }}>
            Older messages →
          </Link>
        </div>
      )}
    </div>
  );
}
