"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { timeAgo } from "@/app/components/ui";
import { ApiError, call } from "@/lib/client";
import type { AssetDetail, LibraryScope, MediaAsset, MediaFolder } from "@/lib/types.media";
import { duration } from "./AssetCard";

function flat(folders: MediaFolder[], depth = 0): { id: string; label: string }[] {
  return folders.flatMap((f) => [{ id: f.id, label: `${"  ".repeat(depth)}${f.name}` }, ...flat(f.children, depth + 1)]);
}

function TagEditor({ asset, scope, onChange }: { asset: MediaAsset; scope: LibraryScope; onChange: (tags: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const [suggest, setSuggest] = useState<string[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!draft.trim()) return setSuggest([]);
    const t = setTimeout(() => {
      call<{ tags: string[] }>(`${scope.apiBase}/tags?q=${encodeURIComponent(draft.trim())}`)
        .then((r) => setSuggest(r.tags.filter((x) => !asset.tags.includes(x))))
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [draft, scope.apiBase, asset.tags]);

  const save = (tags: string[]) =>
    call<{ tags: string[] }>(`${scope.apiBase}/${asset.id}/tags`, { method: "PUT", body: JSON.stringify({ tags }) })
      .then((r) => {
        onChange(r.tags);
        setDraft("");
        setErr("");
      })
      .catch((e) => setErr(e.message));

  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {asset.tags.map((t) => (
          <span key={t} className="pill">
            {t}
            {scope.canEdit && (
              <button className="ml-1" title="Remove" onClick={() => save(asset.tags.filter((x) => x !== t))}>
                ×
              </button>
            )}
          </span>
        ))}
        {asset.tags.length === 0 && !scope.canEdit && (
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            No tags
          </span>
        )}
      </div>
      {scope.canEdit && (
        <div className="relative mt-2">
          <input
            className="input text-xs"
            placeholder="Add a tag and press Enter"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) {
                e.preventDefault();
                save([...asset.tags, draft.trim()]);
              }
            }}
          />
          {suggest.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full rounded-md border bg-white text-xs shadow" style={{ borderColor: "var(--line)" }}>
              {suggest.map((s) => (
                <li key={s} className="cursor-pointer px-2 py-1 hover:bg-neutral-100" onClick={() => save([...asset.tags, s])}>
                  {s}
                </li>
              ))}
            </ul>
          )}
          {err && (
            <p className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
              {err}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function DetailPanel({
  id,
  scope,
  folders,
  onClose,
  onChange,
  onDeleted,
}: {
  id: string;
  scope: LibraryScope;
  folders: MediaFolder[];
  onClose: () => void;
  onChange: (a: MediaAsset) => void;
  onDeleted: () => void;
}) {
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDetail(null);
    setErr("");
    call<AssetDetail>(`${scope.apiBase}/${id}`)
      .then(setDetail)
      .catch((e) => setErr(e.message));
  }, [id, scope.apiBase]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const patch = (a: Partial<MediaAsset>) =>
    setDetail((d) => {
      if (!d) return d;
      const asset = { ...d.asset, ...a };
      onChange(asset);
      return { ...d, asset };
    });

  const act = <T,>(fn: () => Promise<T>) => {
    setBusy(true);
    setErr("");
    return fn()
      .catch((e) => setErr(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  const a = detail?.asset;
  const editable = !!a && scope.canEdit && (scope.shared || !a.is_shared);
  const deletable = !!a && scope.canDelete && (scope.shared || !a.is_shared);
  const isVisual = a?.media_type === "image" || a?.media_type === "gif";

  return (
    <div className="fixed inset-y-0 right-0 z-20 flex w-full max-w-md flex-col overflow-y-auto border-l bg-white shadow-xl" style={{ borderColor: "var(--line)" }} role="dialog">
      <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
        <h2 className="truncate pr-4 text-sm font-semibold">{a?.filename ?? "…"}</h2>
        <button className="btn" onClick={onClose}>
          Close
        </button>
      </div>
      {err && (
        <p className="px-4 pt-3 text-xs" style={{ color: "var(--bad)" }} role="alert">
          {err}
        </p>
      )}
      {a && detail && (
        <div className="space-y-5 p-4 text-sm">
          <div className="overflow-hidden rounded-lg" style={{ background: "#f5f5f5" }}>
            {isVisual ? (
              <img src={a.url} alt={a.alt_text || a.filename} className="max-h-72 w-full object-contain" />
            ) : a.media_type === "video" ? (
              <video src={a.url} controls className="max-h-72 w-full" preload="metadata" />
            ) : (
              <div className="p-6 text-center text-xs uppercase" style={{ color: "var(--muted)" }}>
                {a.media_type}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {editable && (isVisual || a.media_type === "video") && (
              <Link href={`${scope.pageBase}/${a.id}/edit`} className="btn">
                Edit
              </Link>
            )}
            <a href={detail.download_url} className="btn">
              Download
            </a>
            {scope.canUpload && !a.is_shared && (
              <button className="btn" disabled={busy} onClick={() => act(() => call<{ is_starred: boolean }>(`${scope.apiBase}/${a.id}/star`, { method: "POST" }).then((r) => patch({ is_starred: r.is_starred })))}>
                {a.is_starred ? "★ Starred" : "☆ Star"}
              </button>
            )}
            {deletable && (
              <button
                className="btn btn-bad ml-auto"
                disabled={busy}
                onClick={() => {
                  if (window.confirm(scope.shared ? "Delete this shared asset for every workspace? This cannot be undone." : "Delete this file permanently?")) {
                    act(() => call(`${scope.apiBase}/${a.id}`, { method: "DELETE" }).then(onDeleted));
                  }
                }}
              >
                Delete
              </button>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt style={{ color: "var(--muted)" }}>Size</dt>
            <dd>{a.file_size_display}</dd>
            <dt style={{ color: "var(--muted)" }}>Type</dt>
            <dd>{a.mime_type || a.media_type}</dd>
            {a.width > 0 && a.height > 0 && (
              <>
                <dt style={{ color: "var(--muted)" }}>Dimensions</dt>
                <dd>
                  {a.width} × {a.height}px
                </dd>
              </>
            )}
            {a.duration > 0 && (
              <>
                <dt style={{ color: "var(--muted)" }}>Duration</dt>
                <dd>{duration(a.duration)}</dd>
              </>
            )}
            <dt style={{ color: "var(--muted)" }}>Uploaded</dt>
            <dd>
              {new Date(a.created_at).toLocaleString()}
              {a.uploaded_by && ` by ${a.uploaded_by}`}
            </dd>
            <dt style={{ color: "var(--muted)" }}>Status</dt>
            <dd>{a.processing_status}</dd>
            {a.is_shared && (
              <>
                <dt style={{ color: "var(--muted)" }}>Scope</dt>
                <dd>Shared by the organization (read-only here)</dd>
              </>
            )}
          </dl>

          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Tags
            </div>
            <TagEditor asset={a} scope={{ ...scope, canEdit: editable }} onChange={(tags) => patch({ tags })} />
          </div>

          {!scope.shared && editable && folders.length > 0 && (
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                Folder
              </span>
              <select className="input mt-1 text-xs" value={a.folder_id ?? ""} disabled={busy} onChange={(e) => act(() => call<MediaAsset>(`${scope.apiBase}/${a.id}/move`, { method: "POST", body: JSON.stringify({ folder_id: e.target.value || null }) }).then((fresh) => patch(fresh)))}>
                <option value="">No folder</option>
                {flat(folders).map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Versions
            </div>
            {detail.versions.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                No version history yet. Edits will appear here.
              </p>
            ) : (
              <ul className="space-y-1">
                {detail.versions.map((v) => (
                  <li key={v.id} className="flex items-center gap-2 rounded-md px-2 py-1 text-xs" style={{ background: "#fafafa" }}>
                    <span className="font-semibold">v{v.number}</span>
                    {v.is_current && <span className="pill pill-ok">current</span>}
                    <span className="min-w-0 flex-1 truncate" style={{ color: "var(--muted)" }}>
                      {v.description || "—"} · {timeAgo(v.created_at)}
                      {v.created_by && ` · ${v.created_by}`}
                    </span>
                    {!v.is_current && editable && !scope.shared && (
                      <button
                        className="underline"
                        disabled={busy}
                        onClick={() =>
                          window.confirm(`Restore version ${v.number}? This creates a new version.`) &&
                          act(() =>
                            call<AssetDetail>(`${scope.apiBase}/${a.id}/versions/${v.id}/restore`, { method: "POST" }).then((r) => {
                              setDetail((d) => (d ? { ...d, ...r } : d));
                              onChange(r.asset);
                            }),
                          )
                        }
                      >
                        Restore
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
