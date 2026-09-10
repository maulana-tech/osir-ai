"use client";

import { useState } from "react";
import { Empty, Section, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Post } from "@/lib/types";

type Comment = {
  id: string;
  author: string | null;
  author_id: string | null;
  body: string;
  visibility: string;
  attachment_url: string;
  created_at: string;
  replies: Comment[];
};
type Versions = {
  versions: { number: number; created_by: string | null; created_at: string }[];
  old: number | null;
  new: number | null;
  diff: { caption_changed: boolean; caption_diff: { t: string; k: "same" | "add" | "del" }[]; media_changed: boolean; platforms_changed: boolean };
};

function Comments({ workspaceId, postId, userId }: { workspaceId: string; postId: string; userId: string }) {
  const [list, setList] = useState<Comment[] | null>(null);
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState("external");
  const [err, setErr] = useState("");
  const base = `/api/web/workspaces/${workspaceId}/posts/${postId}/comments`;
  const load = () =>
    call<{ comments: Comment[] }>(base)
      .then((r) => setList(r.comments))
      .catch((e) => setErr(e.message));
  if (list === null && !err) void load();

  const Item = ({ c, depth }: { c: Comment; depth: number }) => (
    <li className="py-2 text-sm" style={{ marginLeft: depth * 16 }}>
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
        <span className="font-semibold" style={{ color: "var(--text)" }}>
          {c.author ?? "Deleted user"}
        </span>
        {c.visibility === "internal" && <span className="pill">internal</span>}
        <span>{timeAgo(c.created_at)}</span>
        {c.author_id === userId && (
          <button
            className="underline"
            onClick={() =>
              call(`${base}/${c.id}`, { method: "DELETE" })
                .then(load)
                .catch((e) => setErr(e.message))
            }
          >
            delete
          </button>
        )}
      </div>
      <div className="whitespace-pre-wrap">{c.body}</div>
      {c.attachment_url && (
        <a href={c.attachment_url} className="text-xs underline" target="_blank" rel="noreferrer">
          attachment
        </a>
      )}
      {c.replies.length > 0 && (
        <ul>
          {c.replies.map((r) => (
            <Item key={r.id} c={r} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );

  return (
    <div className="mt-3 rounded-lg border p-3" style={{ borderColor: "var(--line)" }}>
      {err && (
        <p className="text-xs" style={{ color: "var(--bad)" }}>
          {err}
        </p>
      )}
      {list && list.length === 0 && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          No comments yet.
        </p>
      )}
      <ul className="divide-y" style={{ borderColor: "var(--line)" }}>{list?.map((c) => <Item key={c.id} c={c} depth={0} />)}</ul>
      <div className="mt-2 flex gap-2">
        <input className="input" placeholder="Add a comment" value={body} onChange={(e) => setBody(e.target.value)} />
        <select className="input w-auto" value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          <option value="external">Visible to client</option>
          <option value="internal">Team only</option>
        </select>
        <button
          className="btn shrink-0"
          disabled={!body.trim()}
          onClick={() =>
            call(base, { method: "POST", body: JSON.stringify({ body, visibility }) })
              .then(() => {
                setBody("");
                return load();
              })
              .catch((e) => setErr(e.message))
          }
        >
          Post
        </button>
      </div>
    </div>
  );
}

function VersionDiff({ workspaceId, postId }: { workspaceId: string; postId: string }) {
  const [v, setV] = useState<Versions | null>(null);
  const [err, setErr] = useState("");
  if (v === null && !err) {
    call<Versions>(`/api/web/workspaces/${workspaceId}/posts/${postId}/versions`)
      .then(setV)
      .catch((e) => setErr(e.message));
  }
  if (err) return <p className="mt-2 text-xs" style={{ color: "var(--bad)" }}>{err}</p>;
  if (!v) return <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>Loading…</p>;
  return (
    <div className="mt-3 rounded-lg border p-3 text-sm" style={{ borderColor: "var(--line)" }}>
      <div className="mb-2 text-xs" style={{ color: "var(--muted)" }}>
        {v.versions.length} version{v.versions.length === 1 ? "" : "s"}
        {v.old !== null && v.new !== null && ` · showing v${v.old} → v${v.new}`}
        {v.versions[0] && ` · latest by ${v.versions[0].created_by ?? "?"} ${timeAgo(v.versions[0].created_at)}`}
      </div>
      {v.diff.caption_changed ? (
        <p className="whitespace-pre-wrap">
          {v.diff.caption_diff.map((tok, i) =>
            tok.k === "same" ? (
              <span key={i}>{tok.t}</span>
            ) : tok.k === "add" ? (
              <mark key={i} style={{ background: "#0a0a0a", color: "#fff" }}>
                {tok.t}
              </mark>
            ) : (
              <del key={i} style={{ color: "var(--muted)" }}>
                {tok.t}
              </del>
            ),
          )}
        </p>
      ) : (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          Caption unchanged.
        </p>
      )}
      {(v.diff.media_changed || v.diff.platforms_changed) && (
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          {[v.diff.media_changed && "media", v.diff.platforms_changed && "platforms"].filter(Boolean).join(" and ")} changed.
        </p>
      )}
    </div>
  );
}

function Card({ p, workspaceId, userId, selected, onSelect }: { p: Post; workspaceId: string; userId: string; selected: boolean; onSelect: (v: boolean) => void }) {
  const { run, busy, Feedback } = useAction();
  const [comment, setComment] = useState("");
  const [panel, setPanel] = useState<"comments" | "versions" | null>(null);
  const agent = `/api/v1/agent/approvals/${p.id}`;
  const web = `/api/web/workspaces/${workspaceId}/approvals/${p.id}`;
  const onHold = p.status === "on_hold" || p.platform_posts.some((pp) => pp.status === "on_hold");
  const wsInit: RequestInit & { workspaceId: string } = { workspaceId };
  const act = (path: string, body: object, done: string) => run(() => call(path, { ...wsInit, method: "POST", body: JSON.stringify(body) }), done);

  return (
    <li className="rounded-lg border p-4" style={{ borderColor: selected ? "#0a0a0a" : "var(--line)" }}>
      <div className="flex items-start gap-3">
        <input type="checkbox" className="mt-1" checked={selected} onChange={(e) => onSelect(e.target.checked)} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
            {p.platform_posts.map((pp) => (
              <span key={pp.id} className="pill">
                {pp.account_name ?? pp.platform.replace("_", " ")}
              </span>
            ))}
            <span className="pill">{p.status.replace(/_/g, " ")}</span>
            <span>updated {timeAgo(p.updated_at)}</span>
            {p.proposed_publish_at && <span>· proposed {new Date(p.proposed_publish_at).toLocaleString()}</span>}
          </div>
          {p.title && <h3 className="mt-2 font-semibold">{p.title}</h3>}
          <p className="mt-2 whitespace-pre-wrap text-sm">{p.caption}</p>
          {p.first_comment && (
            <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
              First comment: {p.first_comment}
            </p>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {onHold ? (
              <button className="btn btn-ok" disabled={busy} onClick={() => act(`${web}/resume`, {}, "Hold lifted")}>
                Resume
              </button>
            ) : (
              <button className="btn btn-ok" disabled={busy} onClick={() => act(`${agent}/approve`, { comment }, "Approved")}>
                Approve
              </button>
            )}
            <input className="input flex-1" placeholder="Note for the author (required to reject or request changes)" value={comment} onChange={(e) => setComment(e.target.value)} />
            <button className="btn" disabled={busy || !comment.trim()} onClick={() => act(`${web}/request-changes`, { comment }, "Sent back for changes")}>
              Request changes
            </button>
            <button className="btn btn-bad" disabled={busy || !comment.trim()} onClick={() => act(`${agent}/reject`, { comment }, "Rejected")}>
              Reject
            </button>
            <span className="ml-auto flex gap-3 text-xs">
              <button className="underline" style={{ color: "var(--muted)" }} onClick={() => setPanel(panel === "comments" ? null : "comments")}>
                Comments
              </button>
              <button className="underline" style={{ color: "var(--muted)" }} onClick={() => setPanel(panel === "versions" ? null : "versions")}>
                Versions
              </button>
              <a className="underline" style={{ color: "var(--muted)" }} href={`/w/${workspaceId}/compose/${p.id}`}>
                Edit
              </a>
            </span>
          </div>
          <Feedback />
          {panel === "comments" && <Comments workspaceId={workspaceId} postId={p.id} userId={userId} />}
          {panel === "versions" && <VersionDiff workspaceId={workspaceId} postId={p.id} />}
        </div>
      </div>
    </li>
  );
}

export function ApprovalsView({ posts, workspaceId, userId }: { posts: Post[]; workspaceId: string; userId: string }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkComment, setBulkComment] = useState("");
  const bulk = useAction();
  const ids = [...selected].filter((id) => posts.some((p) => p.id === id));
  const doBulk = (action: "approve" | "reject") =>
    bulk.run(async () => {
      const r = await call<{ updated: number; results: { ok: boolean; detail: string }[] }>(`/api/web/workspaces/${workspaceId}/approvals/bulk`, {
        method: "POST",
        body: JSON.stringify({ post_ids: ids, action, comment: bulkComment }),
      });
      setSelected(new Set());
      setBulkComment("");
      const failed = r.results.filter((x) => !x.ok);
      if (failed.length) throw new Error(`${r.updated} updated, ${failed.length} skipped: ${failed[0].detail}`);
    }, `${ids.length} ${action === "approve" ? "approved" : "rejected"}`);

  return (
    <Section title="Waiting for approval" hint={`${posts.length} post${posts.length === 1 ? "" : "s"}`}>
      {posts.length === 0 ? (
        <Empty>Nothing to review. Drafts submitted by the team or the autopilot show up here.</Empty>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={ids.length === posts.length} onChange={(e) => setSelected(e.target.checked ? new Set(posts.map((p) => p.id)) : new Set())} />
              Select all
            </label>
            {ids.length > 0 && (
              <>
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  {ids.length} selected
                </span>
                <button className="btn btn-ok" disabled={bulk.busy} onClick={() => doBulk("approve")}>
                  Approve selected
                </button>
                <input className="input flex-1" placeholder="Rejection note" value={bulkComment} onChange={(e) => setBulkComment(e.target.value)} />
                <button className="btn btn-bad" disabled={bulk.busy || !bulkComment.trim()} onClick={() => doBulk("reject")}>
                  Reject selected
                </button>
              </>
            )}
          </div>
          <bulk.Feedback />
          <ul className="space-y-4">
            {posts.map((p) => (
              <Card
                key={p.id}
                p={p}
                workspaceId={workspaceId}
                userId={userId}
                selected={selected.has(p.id)}
                onSelect={(v) =>
                  setSelected((s) => {
                    const n = new Set(s);
                    if (v) n.add(p.id);
                    else n.delete(p.id);
                    return n;
                  })
                }
              />
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}
