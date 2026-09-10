"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Section, timeAgo } from "@/app/components/ui";
import { ApiError, call } from "@/lib/client";
import type { ComposerAccount, ComposerContext, MediaRef, SaveResult } from "@/lib/types.composer";
import { MediaPicker, uploadToLibrary } from "./MediaPicker";
import { PlatformPanel } from "./PlatformPanels";
import { PreviewCard, wireLength } from "./Preview";

type Override = { title: string; caption: string; first_comment: string };
type Extra = Record<string, unknown>;

const STATUS_PILL: Record<string, string> = {
  draft: "pill",
  pending_review: "pill pill-accent",
  pending_client: "pill pill-accent",
  approved: "pill pill-ok",
  changes_requested: "pill pill-bad",
  rejected: "pill pill-bad",
  scheduled: "pill pill-ok",
  publishing: "pill pill-accent",
  published: "pill pill-ok",
  failed: "pill pill-bad",
  on_hold: "pill",
};

const TRANSITIONS: Record<string, string[]> = {
  draft: ["pending_review", "scheduled"],
  scheduled: ["draft"],
  failed: ["draft", "scheduled"],
  approved: ["scheduled", "draft"],
  changes_requested: ["draft"],
  rejected: ["draft"],
  on_hold: ["approved", "draft"],
  pending_review: [],
  pending_client: [],
  publishing: [],
  published: [],
};

export function ComposerView({ ctx, workspaceId }: { ctx: ComposerContext; workspaceId: string }) {
  const router = useRouter();
  const post = ctx.post;
  const base = `/api/web/workspaces/${workspaceId}/composer`;
  const tpl = ctx.initial.template;

  const [postId, setPostId] = useState<string | null>(post?.id ?? null);
  const [title, setTitle] = useState(post?.title ?? "");
  const [caption, setCaption] = useState(post?.caption ?? tpl?.caption ?? "");
  const [firstComment, setFirstComment] = useState(post?.first_comment ?? tpl?.first_comment ?? ctx.workspace.default_first_comment ?? "");
  const [notes, setNotes] = useState(post?.internal_notes ?? "");
  const [tags, setTags] = useState<string[]>(post?.tags ?? tpl?.tags ?? []);
  const [tagDraft, setTagDraft] = useState("");
  const [categoryId, setCategoryId] = useState(post?.category_id ?? "");
  const [selected, setSelected] = useState<string[]>(post ? post.platform_posts.map((pp) => pp.social_account_id) : (ctx.initial.selected_accounts ?? []));
  const [overrides, setOverrides] = useState<Record<string, Override>>(() => Object.fromEntries((post?.platform_posts ?? []).map((pp) => [pp.social_account_id, { title: pp.title ?? "", caption: pp.caption ?? "", first_comment: pp.first_comment ?? "" }])));
  const [extras, setExtras] = useState<Record<string, Extra>>(() => Object.fromEntries((post?.platform_posts ?? []).map((pp) => [pp.social_account_id, pp.extra ?? {}])));
  const [media, setMedia] = useState<MediaRef[]>(post?.media ?? []);
  const [date, setDate] = useState(post?.scheduled_date ?? ctx.initial.scheduled_date ?? "");
  const [time, setTime] = useState(post?.scheduled_time ?? ctx.initial.scheduled_time ?? "");
  const [recurring, setRecurring] = useState(!!post?.recurrence);
  const [recur, setRecur] = useState(post?.recurrence ?? { frequency: "weekly", interval: 1, end_date: "" });
  const [queueId, setQueueId] = useState("");
  const [openAccount, setOpenAccount] = useState<string | null>(null);
  const [picker, setPicker] = useState<null | { only?: "image"; cb: (a: MediaRef[]) => void }>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  const [statuses, setStatuses] = useState<Record<string, string>>(() => Object.fromEntries((post?.platform_posts ?? []).map((pp) => [pp.id, pp.status])));
  const [dirty, setDirty] = useState(false);
  const [templateName, setTemplateName] = useState<string | null>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  const accounts = ctx.accounts;
  const byId = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a])), [accounts]);
  const selectedAccounts = selected.map((id) => byId[id]).filter(Boolean) as ComposerAccount[];
  const readOnly = !!post?.read_only || (post !== null && !post.can_edit);
  const needsTitle = selectedAccounts.some((a) => a.needs_title);
  const supportsFirstComment = selectedAccounts.length === 0 || selectedAccounts.some((a) => a.supports_first_comment);
  const isCommitted = !!post?.is_committed;

  const markDirty = () => setDirty(true);
  const mark = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    markDirty();
  };

  const payload = useCallback(
    (action: string) => ({
      action,
      title,
      caption,
      first_comment: firstComment,
      internal_notes: notes,
      tags,
      category_id: categoryId || null,
      accounts: selected.map((id) => ({ id, ...(overrides[id] ?? { title: "", caption: "", first_comment: "" }), extra: extras[id] ?? (byId[id] && ["youtube", "pinterest", "tiktok"].includes(byId[id].platform) ? {} : null) })),
      account_scope: ctx.account_scope || null,
      media_asset_ids: media.map((m) => m.id),
      scheduled_date: date || null,
      scheduled_time: time || null,
      queue_id: queueId || null,
      recurring: recurring && action === "schedule" ? recur : null,
    }),
    [title, caption, firstComment, notes, tags, categoryId, selected, overrides, extras, media, date, time, queueId, recurring, recur, ctx.account_scope, byId],
  );

  const save = useCallback(
    async (action: string, done?: string) => {
      setBusy(true);
      setErr("");
      setNotice("");
      try {
        const r = await call<SaveResult>(postId ? `${base}/posts/${postId}` : `${base}/posts`, { method: "POST", body: JSON.stringify(payload(action)) });
        setStatuses(r.platform_statuses);
        setDirty(false);
        if (!postId) {
          setPostId(r.id);
          window.history.replaceState(null, "", `/w/${workspaceId}/compose/${r.id}`);
        }
        if (done) setNotice(done);
        if (action !== "autosave") router.refresh();
        return r;
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Save failed");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [postId, base, payload, workspaceId, router],
  );

  // Autosave every 30s while there are unsaved changes.
  useEffect(() => {
    if (readOnly) return;
    const t = setInterval(() => {
      if (dirty && !busy && (caption.trim() || title.trim() || media.length)) void save("autosave", `Autosaved ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`);
    }, 30000);
    return () => clearInterval(t);
  }, [dirty, busy, caption, title, media.length, save, readOnly]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const toggleAccount = (id: string) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
    markDirty();
  };

  const addTag = (t: string) => {
    const v = t.trim();
    if (v && !tags.includes(v)) mark(setTags)([...tags, v]);
    setTagDraft("");
  };

  async function onDrop(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    try {
      const r = await uploadToLibrary(workspaceId, Array.from(files));
      if (r.errors.length) setErr(r.errors.join("; "));
      mark(setMedia)([...media, ...r.assets]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const move = (i: number, dir: -1 | 1) => {
    const n = [...media];
    const j = i + dir;
    if (j < 0 || j >= n.length) return;
    [n[i], n[j]] = [n[j], n[i]];
    mark(setMedia)(n);
  };

  async function transition(ppId: string, target: string) {
    setErr("");
    try {
      const r = await call<{ status: string }>(`${base}/posts/${postId}/platform-posts/${ppId}/transition`, { method: "POST", body: JSON.stringify({ target_status: target }) });
      setStatuses((s) => ({ ...s, [ppId]: r.status }));
      router.refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not change status");
    }
  }

  const showQueue = ctx.queues.some((q) => selected.includes(q.social_account_id));
  const workflow = ctx.workspace.approval_workflow_mode;
  const canSchedule = ctx.perms.publish_directly && !["required_internal", "required_internal_and_client"].includes(workflow);
  const failed = (post?.platform_posts ?? []).filter((pp) => pp.status === "failed" && pp.publish_error);
  const failedComments = (post?.platform_posts ?? []).filter((pp) => pp.first_comment_status === "failed");

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
      <div className="space-y-4">
        {post?.latest_feedback && (
          <div className="panel p-4 text-sm" style={{ borderColor: "var(--bad)" }}>
            <span className="font-semibold capitalize">{post.latest_feedback.action.replace("_", " ")}:</span> {post.latest_feedback.comment}
          </div>
        )}
        {failed.map((pp) => (
          <div key={pp.id} className="panel p-4 text-sm" style={{ borderColor: "var(--bad)" }}>
            <span className="font-semibold">{byId[pp.social_account_id]?.name ?? pp.platform} failed to publish:</span> {pp.publish_error}
          </div>
        ))}
        {failedComments.map((pp) => (
          <div key={pp.id} className="panel p-4 text-sm" style={{ borderColor: "var(--bad)" }}>
            <span className="font-semibold">{byId[pp.social_account_id]?.name ?? pp.platform}: the first comment failed.</span> {pp.first_comment_error}
          </div>
        ))}
        {readOnly && (
          <div className="panel p-4 text-sm" style={{ color: "var(--muted)" }}>
            {post?.can_edit === false ? "You can only view this post: it belongs to someone else." : "Published posts are read-only. Clone it to post again."}
          </div>
        )}

        <Section title="Channels" hint={selectedAccounts.length ? `${selectedAccounts.length} selected` : undefined}>
          {accounts.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              No connected channels.{" "}
              <Link href={`/w/${workspaceId}/channels`} className="underline">
                Connect one
              </Link>
              .
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {accounts.map((a) => {
                const on = selected.includes(a.id);
                const pp = post?.platform_posts.find((p) => p.social_account_id === a.id);
                const status = pp ? statuses[pp.id] : null;
                return (
                  <div key={a.id} className="flex items-center gap-1 rounded-full border pr-1 pl-1 text-xs" style={{ borderColor: on ? "#0a0a0a" : "var(--line)", background: on ? "#0a0a0a" : "transparent", color: on ? "#fff" : undefined }}>
                    <button className="flex items-center gap-1.5 py-1 pr-1" onClick={() => !readOnly && toggleAccount(a.id)} disabled={readOnly || (!!pp && ["published", "publishing"].includes(pp.status))} title={a.platform}>
                      {a.avatar_url ? <img src={a.avatar_url} alt="" className="h-5 w-5 rounded-full" /> : <span className="inline-flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold uppercase" style={{ background: on ? "#fff" : "#0a0a0a", color: on ? "#0a0a0a" : "#fff" }}>{a.platform.slice(0, 2)}</span>}
                      {a.name}
                    </button>
                    {pp && status && (
                      <select className="rounded-full border-0 bg-transparent py-0.5 text-[10px]" style={{ color: on ? "#fff" : "var(--muted)" }} value={status} onChange={(e) => transition(pp.id, e.target.value)} disabled={readOnly} title="Change this channel's status">
                        <option value={status}>{status.replace(/_/g, " ")}</option>
                        {(TRANSITIONS[status] ?? []).map((t) => (
                          <option key={t} value={t} style={{ color: "#0a0a0a" }}>
                            → {t.replace(/_/g, " ")}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Section>

        <Section title="Content">
          <div className="space-y-3 text-sm">
            {needsTitle && (
              <label className="block">
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  {selectedAccounts.find((a) => a.needs_title)?.title_label ?? "Title"}
                </span>
                <input className="input" value={title} onChange={(e) => mark(setTitle)(e.target.value)} disabled={readOnly} maxLength={255} />
              </label>
            )}
            <label className="block">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                Caption
              </span>
              <textarea className="input min-h-40" value={caption} onChange={(e) => mark(setCaption)(e.target.value)} disabled={readOnly} placeholder="Write your post…" />
            </label>
            {selectedAccounts.length > 0 && (
              <div className="flex flex-wrap gap-3 text-xs" style={{ color: "var(--muted)" }}>
                {selectedAccounts.map((a) => {
                  const text = overrides[a.id]?.caption || caption;
                  const n = wireLength(text, a.escaped_chars);
                  return (
                    <span key={a.id} style={{ color: n > a.char_limit ? "var(--bad)" : undefined }}>
                      {a.name}: {n}/{a.char_limit}
                    </span>
                  );
                })}
                {ctx.workspace.default_hashtags.length > 0 && (
                  <button className="underline" onClick={() => mark(setCaption)(`${caption.trimEnd()}\n\n${ctx.workspace.default_hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ")}`)} disabled={readOnly}>
                    add default hashtags
                  </button>
                )}
              </div>
            )}

            <div
              ref={dropRef}
              className="rounded-lg border border-dashed p-3"
              style={{ borderColor: "var(--line)" }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!readOnly) onDrop(e.dataTransfer.files);
              }}
            >
              <div className="mb-2 flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                <span>Media</span>
                {!readOnly && (
                  <>
                    <button className="btn ml-auto" onClick={() => setPicker({ cb: (a) => mark(setMedia)([...media, ...a]) })}>
                      Add media
                    </button>
                    <Link href={`/w/${workspaceId}/media`} className="underline">
                      library
                    </Link>
                  </>
                )}
              </div>
              {media.length === 0 ? (
                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  Drop images or videos here, or add from the library{ctx.unsplash_enabled ? " or Unsplash" : ""}.
                </p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {media.map((m, i) => (
                    <li key={m.id} className="relative h-24 w-24 overflow-hidden rounded-lg border" style={{ borderColor: "var(--line)" }} title={m.filename}>
                      {m.media_type === "video" ? <video src={m.url} className="h-full w-full object-cover" muted /> : <img src={m.thumbnail_url ?? m.url} alt="" className="h-full w-full object-cover" />}
                      {!readOnly && (
                        <div className="absolute inset-x-0 bottom-0 flex justify-between px-1 text-[10px]" style={{ background: "rgba(255,255,255,0.85)" }}>
                          <button onClick={() => move(i, -1)} disabled={i === 0}>
                            ←
                          </button>
                          <button onClick={() => mark(setMedia)(media.filter((x) => x.id !== m.id))} style={{ color: "var(--bad)" }}>
                            remove
                          </button>
                          <button onClick={() => move(i, 1)} disabled={i === media.length - 1}>
                            →
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {supportsFirstComment && (
              <label className="block">
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  First comment (optional)
                </span>
                <textarea className="input" rows={2} value={firstComment} onChange={(e) => mark(setFirstComment)(e.target.value)} disabled={readOnly} />
              </label>
            )}
            {ctx.perms.view_internal_notes && (
              <label className="block">
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  Internal notes (never published, hidden from clients)
                </span>
                <textarea className="input" rows={2} value={notes} onChange={(e) => mark(setNotes)(e.target.value)} disabled={readOnly} />
              </label>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  Tags
                </span>
                <div className="flex flex-wrap gap-1">
                  {tags.map((t) => (
                    <span key={t} className="pill">
                      {t}
                      {!readOnly && (
                        <button className="ml-1" onClick={() => mark(setTags)(tags.filter((x) => x !== t))}>
                          ×
                        </button>
                      )}
                    </span>
                  ))}
                </div>
                {!readOnly && (
                  <input
                    className="input mt-1"
                    list="composer-tags"
                    placeholder="Add a tag, press Enter"
                    value={tagDraft}
                    onChange={(e) => setTagDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === ",") {
                        e.preventDefault();
                        addTag(tagDraft);
                      }
                    }}
                  />
                )}
                <datalist id="composer-tags">
                  {ctx.tags.map((t) => (
                    <option key={t} value={t} />
                  ))}
                </datalist>
              </div>
              <label className="block">
                <span className="text-xs" style={{ color: "var(--muted)" }}>
                  Category
                </span>
                <select className="input" value={categoryId} onChange={(e) => mark(setCategoryId)(e.target.value)} disabled={readOnly}>
                  <option value="">None</option>
                  {ctx.categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </Section>

        {selectedAccounts.length > 0 && (
          <Section title="Per-channel settings">
            <div className="divide-y" style={{ borderColor: "var(--line)" }}>
              {selectedAccounts.map((a) => {
                const o = overrides[a.id] ?? { title: "", caption: "", first_comment: "" };
                const open = openAccount === a.id;
                const hasPanel = ["youtube", "pinterest", "tiktok"].includes(a.platform);
                const customised = !!(o.title || o.caption || o.first_comment);
                return (
                  <div key={a.id} className="py-2 text-sm">
                    <button className="flex w-full items-center gap-2 text-left" onClick={() => setOpenAccount(open ? null : a.id)}>
                      <span className="font-semibold">{a.name}</span>
                      <span className="pill">{a.platform.replace("_", " ")}</span>
                      {customised && <span className="pill pill-accent">customised</span>}
                      {hasPanel && !customised && (
                        <span className="text-xs" style={{ color: "var(--muted)" }}>
                          has platform options
                        </span>
                      )}
                      <span className="ml-auto text-xs" style={{ color: "var(--muted)" }}>
                        {open ? "hide" : "edit"}
                      </span>
                    </button>
                    {open && (
                      <div className="mt-2 space-y-2 pl-1">
                        {a.needs_title && (
                          <label className="block">
                            <span className="text-xs" style={{ color: "var(--muted)" }}>
                              {a.title_label} override{a.title_max_length ? ` (max ${a.title_max_length})` : ""}
                            </span>
                            <input className="input" value={o.title} maxLength={a.title_max_length || undefined} disabled={readOnly} onChange={(e) => mark(setOverrides)({ ...overrides, [a.id]: { ...o, title: e.target.value } })} placeholder={title || "Uses the shared title"} />
                          </label>
                        )}
                        <label className="block">
                          <span className="text-xs" style={{ color: "var(--muted)" }}>
                            {a.caption_label} override
                          </span>
                          <textarea className="input" rows={3} value={o.caption} disabled={readOnly} onChange={(e) => mark(setOverrides)({ ...overrides, [a.id]: { ...o, caption: e.target.value } })} placeholder="Leave empty to use the shared caption" />
                        </label>
                        {a.supports_first_comment && (
                          <label className="block">
                            <span className="text-xs" style={{ color: "var(--muted)" }}>
                              First comment override
                            </span>
                            <textarea className="input" rows={2} value={o.first_comment} disabled={readOnly} onChange={(e) => mark(setOverrides)({ ...overrides, [a.id]: { ...o, first_comment: e.target.value } })} />
                          </label>
                        )}
                        {hasPanel && (
                          <PlatformPanel
                            workspaceId={workspaceId}
                            account={a}
                            extra={extras[a.id] ?? {}}
                            media={media}
                            onChange={(e) => mark(setExtras)({ ...extras, [a.id]: e })}
                            pickImage={(cb) => setPicker({ only: "image", cb: (list) => list[0] && cb(list[0]) })}
                          />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {post && post.approval_history.length > 0 && (
          <Section title="Approval history">
            <ul className="space-y-1 text-xs">
              {post.approval_history.map((h, i) => (
                <li key={i}>
                  <span className="font-semibold capitalize">{h.action.replace("_", " ")}</span>
                  {h.user && ` by ${h.user}`} · {timeAgo(h.created_at)}
                  {h.comment && <span style={{ color: "var(--muted)" }}> — {h.comment}</span>}
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      <aside className="space-y-4">
        <Section title="Preview">
          {selectedAccounts.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Pick a channel to preview.
            </p>
          ) : (
            <div className="space-y-3">
              {selectedAccounts.map((a) => (
                <PreviewCard key={a.id} account={a} title={overrides[a.id]?.title || title} caption={overrides[a.id]?.caption || caption} firstComment={overrides[a.id]?.first_comment || firstComment} media={media} />
              ))}
            </div>
          )}
        </Section>

        {!readOnly && (
          <Section title={isCommitted ? "Schedule" : "Schedule (proposed until scheduled)"}>
            <div className="space-y-2 text-sm">
              <div className="flex gap-2">
                <input className="input" type="date" value={date} onChange={(e) => mark(setDate)(e.target.value)} />
                <input className="input" type="time" value={time} onChange={(e) => mark(setTime)(e.target.value)} />
              </div>
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                Times are in {ctx.workspace.timezone}.{post?.schedule_is_proposed && " This is the proposed time; Save draft keeps it as a proposal."}
              </p>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={recurring} onChange={(e) => mark(setRecurring)(e.target.checked)} />
                Repeat
              </label>
              {recurring && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  every
                  <input className="input w-16" type="number" min={1} value={recur.interval} onChange={(e) => mark(setRecur)({ ...recur, interval: Number(e.target.value) || 1 })} />
                  <select className="input w-auto" value={recur.frequency} onChange={(e) => mark(setRecur)({ ...recur, frequency: e.target.value })}>
                    <option value="daily">day(s)</option>
                    <option value="weekly">week(s)</option>
                    <option value="monthly">month(s)</option>
                  </select>
                  until
                  <input className="input w-auto" type="date" value={recur.end_date} onChange={(e) => mark(setRecur)({ ...recur, end_date: e.target.value })} />
                </div>
              )}
              {showQueue && (
                <select className="input" value={queueId} onChange={(e) => setQueueId(e.target.value)}>
                  <option value="">Queue: every selected channel&apos;s queue</option>
                  {ctx.queues
                    .filter((q) => selected.includes(q.social_account_id))
                    .map((q) => (
                      <option key={q.id} value={q.id}>
                        Queue: {q.name} ({q.account_name})
                      </option>
                    ))}
                </select>
              )}
            </div>
          </Section>
        )}

        {!readOnly && (
          <Section title="Actions">
            <div className="flex flex-wrap gap-2 text-sm">
              <button className="btn" disabled={busy} onClick={() => save("save_draft", "Draft saved")}>
                Save draft
              </button>
              {canSchedule && (
                <button className="btn btn-accent" disabled={busy || !selected.length || !date || !time} onClick={() => save("schedule", "Scheduled")} title={!date || !time ? "Pick a date and time" : ""}>
                  Schedule
                </button>
              )}
              {ctx.perms.publish_directly && (
                <button className="btn btn-ok" disabled={busy || !selected.length} onClick={() => window.confirm("Publish to the selected channels now?") && save("publish_now", "Publishing")}>
                  Publish now
                </button>
              )}
              {showQueue && canSchedule && (
                <>
                  <button className="btn" disabled={busy || !selected.length} onClick={() => save("add_to_queue", "Added to queue")}>
                    Next available slot
                  </button>
                  <button className="btn" disabled={busy || !selected.length} onClick={() => save("add_to_queue_priority", "Added to the front of the queue")}>
                    Front of queue
                  </button>
                </>
              )}
              {workflow !== "none" && (post ? post.show_submit : true) && (
                <button className="btn btn-accent" disabled={busy || !selected.length} onClick={() => save("submit_for_approval", "Submitted for approval")}>
                  Submit for approval
                </button>
              )}
              {post?.show_resubmit && (
                <button className="btn btn-accent" disabled={busy} onClick={() => save("resubmit_for_approval", "Resubmitted")}>
                  Resubmit for review
                </button>
              )}
            </div>
            {err && (
              <p className="mt-2 text-sm" style={{ color: "var(--bad)" }} role="alert">
                {err}
              </p>
            )}
            {notice && !err && (
              <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
                {notice}
              </p>
            )}
            {dirty && !notice && (
              <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
                Unsaved changes (autosaves every 30 s).
              </p>
            )}
          </Section>
        )}

        {postId && (
          <Section title="More">
            <div className="flex flex-wrap gap-2 text-sm">
              <button
                className="btn"
                disabled={busy}
                onClick={async () => {
                  const r = await call<{ id: string }>(`${base}/posts/${postId}/clone`, { method: "POST" }).catch((e) => setErr(e.message));
                  if (r) router.push(`/w/${workspaceId}/compose/${r.id}`);
                }}
              >
                Clone as draft
              </button>
              <button className="btn" onClick={() => setTemplateName(templateName === null ? "" : null)}>
                Save as template
              </button>
              <Link href={`/w/${workspaceId}/approvals`} className="btn">
                Comments
              </Link>
              {post?.can_edit && (
                <button
                  className="btn btn-bad ml-auto"
                  disabled={busy}
                  onClick={async () => {
                    if (!window.confirm("Delete this post for every channel?")) return;
                    await call(`${base}/posts/${postId}`, { method: "DELETE" }).catch((e) => setErr(e.message));
                    router.push(`/w/${workspaceId}/calendar?view=list&tab=drafts`);
                  }}
                >
                  Delete
                </button>
              )}
            </div>
            {templateName !== null && (
              <div className="mt-2 flex gap-2">
                <input className="input" placeholder="Template name" value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
                <button
                  className="btn btn-accent shrink-0"
                  onClick={async () => {
                    await call(`${base}/posts/${postId}/save-as-template`, { method: "POST", body: JSON.stringify({ name: templateName }) }).catch((e) => setErr(e.message));
                    setTemplateName(null);
                    setNotice("Template saved");
                  }}
                >
                  Save
                </button>
              </div>
            )}
            {post && (
              <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
                {post.versions_count} version{post.versions_count === 1 ? "" : "s"} · last saved {timeAgo(post.updated_at)}
                {post.author && ` · by ${post.author}`}
              </p>
            )}
          </Section>
        )}
      </aside>

      {picker && (
        <MediaPicker
          workspaceId={workspaceId}
          only={picker.only}
          multiple={!picker.only}
          unsplash={ctx.unsplash_enabled}
          onPick={picker.cb}
          onClose={() => setPicker(null)}
        />
      )}
    </div>
  );
}
