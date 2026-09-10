"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MediaPicker } from "@/app/components/composer/MediaPicker";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Board, Idea, MediaRef } from "@/lib/types.composer";

type Draft = { id?: string; title: string; description: string; tags: string[]; group_id: string; media: MediaRef[] };

function IdeaForm({ workspaceId, draft, onClose, unsplash }: { workspaceId: string; draft: Draft; onClose: () => void; unsplash: boolean }) {
  const { run, busy, Feedback } = useAction();
  const [d, setD] = useState(draft);
  const [tagDraft, setTagDraft] = useState("");
  const [picker, setPicker] = useState(false);
  const base = `/api/web/workspaces/${workspaceId}/composer/ideas`;
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }} onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()} role="dialog">
        <h2 className="mb-3 text-sm font-semibold">{d.id ? "Edit idea" : "New idea"}</h2>
        <div className="space-y-2 text-sm">
          <input className="input" placeholder="Title" value={d.title} autoFocus onChange={(e) => setD({ ...d, title: e.target.value })} />
          <textarea className="input" rows={4} placeholder="Notes, angle, draft copy…" value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} />
          <div className="flex flex-wrap gap-1">
            {d.tags.map((t) => (
              <span key={t} className="pill">
                {t}
                <button className="ml-1" onClick={() => setD({ ...d, tags: d.tags.filter((x) => x !== t) })}>
                  ×
                </button>
              </span>
            ))}
            <input
              className="input w-40 py-0.5 text-xs"
              placeholder="tag + Enter"
              value={tagDraft}
              onChange={(e) => setTagDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && tagDraft.trim()) {
                  e.preventDefault();
                  if (!d.tags.includes(tagDraft.trim())) setD({ ...d, tags: [...d.tags, tagDraft.trim()] });
                  setTagDraft("");
                }
              }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {d.media.map((m) => (
              <span key={m.id} className="relative h-14 w-14 overflow-hidden rounded border" style={{ borderColor: "var(--line)" }}>
                <img src={m.thumbnail_url ?? m.url} alt="" className="h-full w-full object-cover" />
                <button className="absolute top-0 right-0 px-1 text-[10px]" style={{ background: "rgba(255,255,255,0.9)" }} onClick={() => setD({ ...d, media: d.media.filter((x) => x.id !== m.id) })}>
                  ×
                </button>
              </span>
            ))}
            <button className="btn" onClick={() => setPicker(true)}>
              Add media
            </button>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn btn-accent"
              disabled={busy || !d.title.trim()}
              onClick={async () => {
                const body = { title: d.title, description: d.description, tags: d.tags, group_id: d.group_id || null, media_asset_ids: d.media.map((m) => m.id) };
                const r = await run(() => call(d.id ? `${base}/${d.id}` : base, { method: d.id ? "PATCH" : "POST", body: JSON.stringify(body) }));
                if (r !== undefined) onClose();
              }}
            >
              Save
            </button>
          </div>
          <Feedback />
        </div>
        {picker && <MediaPicker workspaceId={workspaceId} unsplash={unsplash} onPick={(a) => setD((x) => ({ ...x, media: [...x.media, ...a] }))} onClose={() => setPicker(false)} />}
      </div>
    </div>
  );
}

export function IdeasBoard({ workspaceId, board, unsplash }: { workspaceId: string; board: Board; unsplash: boolean }) {
  const router = useRouter();
  const { run, busy, Feedback } = useAction();
  const [editing, setEditing] = useState<Draft | null>(null);
  const [newCol, setNewCol] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const base = `/api/web/workspaces/${workspaceId}/composer`;

  const toDraft = (i: Idea): Draft => ({ id: i.id, title: i.title, description: i.description, tags: i.tags, group_id: i.group_id ?? "", media: i.media.map((m) => ({ id: m.asset_id, url: m.url, thumbnail_url: m.thumbnail_url, filename: m.filename, media_type: m.media_type })) });

  async function dropOn(groupId: string, position: number) {
    if (!dragging) return;
    const id = dragging;
    setDragging(null);
    await run(() => call(`${base}/ideas/${id}/move`, { method: "POST", body: JSON.stringify({ group_id: groupId, position }) }));
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <button className="btn btn-accent" onClick={() => setEditing({ title: "", description: "", tags: [], group_id: board.columns[0]?.id ?? "", media: [] })}>
          New idea
        </button>
        <select className="input w-auto" value={board.active_tag} onChange={(e) => router.push(`/w/${workspaceId}/create?tab=ideas${e.target.value ? `&tag=${encodeURIComponent(e.target.value)}` : ""}`)}>
          <option value="">All tags</option>
          {board.tags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button className="btn ml-auto" onClick={() => setNewCol("")}>
          Add column
        </button>
      </div>
      {newCol !== null && (
        <div className="mb-3 flex gap-2">
          <input className="input w-60" placeholder="Column name" value={newCol} autoFocus onChange={(e) => setNewCol(e.target.value)} />
          <button
            className="btn btn-accent"
            disabled={busy || !newCol.trim()}
            onClick={async () => {
              const r = await run(() => call(`${base}/idea-groups`, { method: "POST", body: JSON.stringify({ name: newCol }) }));
              if (r !== undefined) setNewCol(null);
            }}
          >
            Add
          </button>
          <button className="btn" onClick={() => setNewCol(null)}>
            Cancel
          </button>
        </div>
      )}
      <Feedback />
      <div className="flex gap-3 overflow-x-auto pb-2">
        {board.columns.map((col) => (
          <div
            key={col.id}
            className="flex w-64 shrink-0 flex-col rounded-lg p-2"
            style={{ background: dragging ? "#f5f5f5" : "#fafafa", minHeight: 200 }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              dropOn(col.id, col.ideas.length);
            }}
          >
            <div className="mb-2 flex items-center justify-between px-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              <span>
                {col.name} <span className="font-normal">{col.ideas.length}</span>
              </span>
              {col.ideas.length === 0 && (
                <button title="Delete empty column" onClick={() => window.confirm(`Delete column "${col.name}"?`) && run(() => call(`${base}/idea-groups/${col.id}`, { method: "DELETE" }))}>
                  ×
                </button>
              )}
            </div>
            <ul className="space-y-2">
              {col.ideas.map((i, idx) => (
                <li
                  key={i.id}
                  draggable
                  onDragStart={() => setDragging(i.id)}
                  onDragEnd={() => setDragging(null)}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dropOn(col.id, idx);
                  }}
                  onDragOver={(e) => e.preventDefault()}
                  className="cursor-grab rounded-lg border bg-white p-3 text-sm"
                  style={{ borderColor: "var(--line)", opacity: dragging === i.id ? 0.5 : 1 }}
                >
                  {i.media[0] && (
                    <div className="mb-2 h-24 overflow-hidden rounded" style={{ background: "#f5f5f5" }}>
                      <img src={i.media[0].thumbnail_url ?? i.media[0].url} alt="" className="h-full w-full object-cover" />
                    </div>
                  )}
                  <div className="font-semibold">{i.title}</div>
                  {i.description && (
                    <p className="mt-1 line-clamp-3 text-xs" style={{ color: "var(--muted)" }}>
                      {i.description}
                    </p>
                  )}
                  {i.tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {i.tags.map((t) => (
                        <span key={t} className="pill">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 flex gap-2 text-xs" style={{ color: "var(--muted)" }}>
                    {i.post_id ? (
                      <a href={`/w/${workspaceId}/compose/${i.post_id}`} className="underline">
                        open post
                      </a>
                    ) : (
                      <button
                        className="underline"
                        disabled={busy}
                        onClick={async () => {
                          const r = await run(() => call<{ post_id: string }>(`${base}/ideas/${i.id}/create-post`, { method: "POST" }));
                          if (r) router.push(`/w/${workspaceId}/compose/${r.post_id}`);
                        }}
                      >
                        create post
                      </button>
                    )}
                    <button className="underline" onClick={() => setEditing(toDraft(i))}>
                      edit
                    </button>
                    <button className="ml-auto underline" style={{ color: "var(--bad)" }} onClick={() => window.confirm(`Delete "${i.title}"?`) && run(() => call(`${base}/ideas/${i.id}`, { method: "DELETE" }))}>
                      delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {editing && <IdeaForm workspaceId={workspaceId} draft={editing} unsplash={unsplash} onClose={() => setEditing(null)} />}
    </div>
  );
}
