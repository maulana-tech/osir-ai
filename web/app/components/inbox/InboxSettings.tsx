"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Section } from "@/app/components/ui";
import { ApiError, call } from "@/lib/client";
import type { Sla } from "@/lib/types.inbox";

type Saved = { id: string; title: string; body: string };

export function InboxSettings({ workspaceId, savedReplies, sla }: { workspaceId: string; savedReplies: Saved[]; sla: Sla }) {
  const router = useRouter();
  const base = `/api/web/workspaces/${workspaceId}/inbox`;
  const [editing, setEditing] = useState<Saved | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [form, setForm] = useState<Sla>(sla);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
    }
  }

  const submitReply = () =>
    run(async () => {
      if (editing) await call(`${base}/saved-replies/${editing.id}`, { method: "PUT", body: JSON.stringify({ title, body }) });
      else await call(`${base}/saved-replies`, { method: "POST", body: JSON.stringify({ title, body }) });
      setEditing(null);
      setTitle("");
      setBody("");
    });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Saved replies" hint={`${savedReplies.length}`}>
        <ul className="mb-4 divide-y" style={{ borderColor: "var(--line)" }}>
          {savedReplies.map((r) => (
            <li key={r.id} className="flex items-start gap-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{r.title}</div>
                <p className="line-clamp-2 text-xs" style={{ color: "var(--muted)" }}>
                  {r.body}
                </p>
              </div>
              <button
                className="btn"
                onClick={() => {
                  setEditing(r);
                  setTitle(r.title);
                  setBody(r.body);
                }}
              >
                Edit
              </button>
              <button className="btn btn-bad" onClick={() => run(() => call(`${base}/saved-replies/${r.id}`, { method: "DELETE" }))}>
                Delete
              </button>
            </li>
          ))}
        </ul>
        <div className="space-y-2">
          <input className="input" placeholder="Title (e.g. Shipping)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className="input" rows={3} placeholder="Reply text" value={body} onChange={(e) => setBody(e.target.value)} />
          <div className="flex justify-end gap-2">
            {editing && (
              <button
                className="btn"
                onClick={() => {
                  setEditing(null);
                  setTitle("");
                  setBody("");
                }}
              >
                Cancel
              </button>
            )}
            <button className="btn btn-accent" disabled={!title.trim() || !body.trim()} onClick={submitReply}>
              {editing ? "Save changes" : "Add saved reply"}
            </button>
          </div>
        </div>
      </Section>

      <Section title="Response SLA">
        <div className="space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Track response time
          </label>
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Target first response (minutes)
            </span>
            <input type="number" min={1} className="input" value={form.target_response_minutes} onChange={(e) => setForm({ ...form, target_response_minutes: Number(e.target.value) })} />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.auto_resolve_on_reply} onChange={(e) => setForm({ ...form, auto_resolve_on_reply: e.target.checked })} /> Resolve a message automatically when someone replies
          </label>
          <div className="flex items-center justify-end gap-3">
            {saved && (
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                Saved
              </span>
            )}
            <button
              className="btn btn-accent"
              onClick={() =>
                run(async () => {
                  await call(`${base}/sla`, { method: "PUT", body: JSON.stringify(form) });
                  setSaved(true);
                })
              }
            >
              Save
            </button>
          </div>
        </div>
      </Section>
      {error && (
        <div className="rounded-lg border px-3 py-2 text-sm lg:col-span-2" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          {error}
        </div>
      )}
    </div>
  );
}
