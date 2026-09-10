"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { timeAgo } from "@/app/components/ui";
import { ApiError, call } from "@/lib/client";
import type { InboxDetail, Member } from "@/lib/types.inbox";

export function ThreadPane({
  workspaceId,
  message,
  team,
  canReply,
}: {
  workspaceId: string;
  message: InboxDetail;
  team: Member[];
  canReply: boolean;
}) {
  const router = useRouter();
  const base = `/api/web/workspaces/${workspaceId}/inbox/${message.id}`;
  const [reply, setReply] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const sendReply = () =>
    run(async () => {
      await call(`${base}/reply`, { method: "POST", body: JSON.stringify({ body: reply }) });
      setReply("");
    });
  const addNote = () =>
    run(async () => {
      await call(`${base}/note`, { method: "POST", body: JSON.stringify({ body: note }) });
      setNote("");
    });
  const triage = (patch: { status?: string; sentiment?: string }) =>
    run(() => call(`${base}/triage`, { method: "POST", body: JSON.stringify(patch) }));
  const assign = (user_id: string | null) => run(() => call(`${base}/assign`, { method: "POST", body: JSON.stringify({ user_id }) }));

  return (
    <div className="space-y-5">
      <header>
        <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
          <span className="pill">{message.message_type}</span>
          <span>{message.account.name}</span>
          <span>· {new Date(message.received_at).toLocaleString()}</span>
          {message.related_post && (
            <a href={`/w/${workspaceId}/compose/${message.related_post.id}`} className="hover:text-black">
              on your post “{message.related_post.caption.slice(0, 40)}…”
            </a>
          )}
        </div>
        <h2 className="mt-1 text-lg font-semibold">
          {message.sender_name}{" "}
          {message.sender_handle && (
            <span className="text-sm font-normal" style={{ color: "var(--muted)" }}>
              @{message.sender_handle}
            </span>
          )}
        </h2>
      </header>

      {message.parent && (
        <blockquote className="rounded-lg border-l-4 px-3 py-2 text-sm" style={{ borderColor: "#e5e5e5", color: "var(--muted)" }}>
          {message.parent.sender_name}: {message.parent.body}
        </blockquote>
      )}
      <p className="whitespace-pre-wrap text-sm">{message.body}</p>

      {canReply && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select className="input w-auto" value={message.status} disabled={busy} onChange={(e) => triage({ status: e.target.value })} aria-label="Status">
            {["unread", "open", "resolved", "archived"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select className="input w-auto" value={message.sentiment} disabled={busy} onChange={(e) => triage({ sentiment: e.target.value })} aria-label="Sentiment">
            <option value="">sentiment…</option>
            {["positive", "neutral", "negative"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select className="input w-auto" value={message.assigned_to?.id ?? ""} disabled={busy} onChange={(e) => assign(e.target.value || null)} aria-label="Assignee">
            <option value="">unassigned</option>
            {team.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {error && (
        <div className="rounded-lg border px-3 py-2 text-sm" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          {error}
        </div>
      )}

      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
          Thread
        </h3>
        {message.thread.length === 0 && (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            No replies yet.
          </p>
        )}
        <ul className="space-y-2">
          {message.thread.map((t) => (
            <li key={t.id} className="rounded-lg border px-3 py-2 text-sm" style={t.kind === "note" ? { borderColor: "#e5e5e5", background: "#fafafa" } : { borderColor: "#0a0a0a" }}>
              <div className="mb-1 flex items-center gap-2 text-[11px]" style={{ color: "var(--muted)" }}>
                <span className="pill">{t.kind === "note" ? "internal note" : t.delivered ? "reply" : "reply (not delivered)"}</span>
                <span>{t.author ?? "—"}</span>
                <span>· {timeAgo(t.at)}</span>
              </div>
              <p className="whitespace-pre-wrap">{t.body}</p>
            </li>
          ))}
        </ul>
      </section>

      {message.children.length > 0 && (
        <section>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Replies from others
          </h3>
          <ul className="space-y-1 text-sm">
            {message.children.map((c) => (
              <li key={c.id}>
                <span className="font-semibold">{c.sender_name}</span>: {c.body}
              </li>
            ))}
          </ul>
        </section>
      )}

      {canReply && (
        <section className="space-y-3">
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                Reply publicly
              </label>
              {message.saved_replies.length > 0 && (
                <select className="input w-auto" defaultValue="" onChange={(e) => setReply(message.saved_replies.find((r) => r.id === e.target.value)?.body ?? reply)} aria-label="Saved reply">
                  <option value="">insert saved reply…</option>
                  {message.saved_replies.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <textarea className="input" rows={3} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write a reply that goes to the platform" />
            <div className="mt-2 flex justify-end">
              <button className="btn btn-accent" disabled={busy || !reply.trim()} onClick={sendReply}>
                Send reply
              </button>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Internal note
            </label>
            <textarea className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Only your team sees this" />
            <div className="mt-2 flex justify-end">
              <button className="btn" disabled={busy || !note.trim()} onClick={addNote}>
                Add note
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
