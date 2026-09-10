"use client";

import { useEffect, useRef, useState } from "react";
import { call } from "@/lib/client";
import type { MediaRef } from "@/lib/types.composer";
import type { Library, MediaAsset } from "@/lib/types.media";

function csrf() {
  return decodeURIComponent(document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] ?? "");
}

export function toRef(a: MediaAsset): MediaRef {
  return { id: a.id, url: a.url, thumbnail_url: a.thumbnail_url, filename: a.filename, media_type: a.media_type, width: a.width, height: a.height, duration: a.duration };
}

/** Upload files to the workspace library; resolves with the created assets. */
export async function uploadToLibrary(workspaceId: string, files: File[]): Promise<{ assets: MediaRef[]; errors: string[] }> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(`/api/web/workspaces/${workspaceId}/media/upload`, { method: "POST", body: fd, headers: { "X-CSRFToken": csrf() } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? "Upload failed");
  const assets: MediaRef[] = [];
  const errors: string[] = [];
  for (const r of body.results ?? []) {
    if (r.ok) assets.push(toRef(r.asset));
    else errors.push(`${r.filename}: ${r.error}`);
  }
  return { assets, errors };
}

/**
 * Modal for choosing from the library (with search and type filter),
 * uploading, or importing from Unsplash. Calls onPick with the chosen assets.
 */
export function MediaPicker({
  workspaceId,
  onPick,
  onClose,
  only,
  unsplash,
  multiple = true,
}: {
  workspaceId: string;
  onPick: (assets: MediaRef[]) => void;
  onClose: () => void;
  only?: "image" | "video";
  unsplash?: boolean;
  multiple?: boolean;
}) {
  const [tab, setTab] = useState<"library" | "unsplash">("library");
  const [q, setQ] = useState("");
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [photos, setPhotos] = useState<Record<string, unknown>[]>([]);
  const [uq, setUq] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const base = `/api/web/workspaces/${workspaceId}`;

  useEffect(() => {
    const p = new URLSearchParams({ sort: "-date" });
    if (q.trim()) p.set("q", q.trim());
    if (only) p.set("type", only);
    const t = setTimeout(() => {
      call<Library>(`${base}/media?${p}`)
        .then((r) => setAssets(r.assets.filter((a) => !only || a.media_type === only || (only === "image" && a.media_type === "gif"))))
        .catch((e) => setErr(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [q, only, base]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (id: string) =>
    setChosen((s) => {
      const n = new Set(multiple ? s : []);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setErr("");
    try {
      const r = await uploadToLibrary(workspaceId, Array.from(files));
      if (r.errors.length) setErr(r.errors.join("; "));
      if (r.assets.length) {
        onPick(r.assets);
        onClose();
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function searchUnsplash() {
    setBusy(true);
    setErr("");
    try {
      const r = await call<{ results: Record<string, unknown>[] }>(`${base}/composer/unsplash?q=${encodeURIComponent(uq)}`);
      setPhotos(r.results);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  async function importUnsplash() {
    const selected = photos.filter((p) => chosen.has(String(p.id)));
    if (!selected.length) return;
    setBusy(true);
    setErr("");
    try {
      const r = await call<{ assets: MediaRef[]; failed: number }>(`${base}/composer/unsplash/import`, { method: "POST", body: JSON.stringify({ photos: selected }) });
      onPick(r.assets);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }} onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()} role="dialog">
        <div className="flex items-center gap-2 border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
          <button className={`btn ${tab === "library" ? "btn-accent" : ""}`} onClick={() => setTab("library")}>
            Library
          </button>
          {unsplash && (
            <button className={`btn ${tab === "unsplash" ? "btn-accent" : ""}`} onClick={() => setTab("unsplash")}>
              Unsplash
            </button>
          )}
          <button className="btn" disabled={busy} onClick={() => fileInput.current?.click()}>
            Upload
          </button>
          <input ref={fileInput} type="file" multiple={multiple} accept={only === "image" ? "image/*" : only === "video" ? "video/*" : "image/*,video/*"} className="hidden" onChange={(e) => upload(e.target.files)} />
          <button className="btn ml-auto" onClick={onClose}>
            Close
          </button>
        </div>
        {err && (
          <p className="px-4 pt-2 text-xs" style={{ color: "var(--bad)" }}>
            {err}
          </p>
        )}
        {tab === "library" ? (
          <>
            <div className="px-4 pt-3">
              <input className="input" type="search" placeholder="Search the library" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
            </div>
            <div className="grid flex-1 gap-2 overflow-y-auto p-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
              {assets.map((a) => (
                <button key={a.id} className="relative aspect-square overflow-hidden rounded-lg border" style={{ borderColor: chosen.has(a.id) ? "#0a0a0a" : "var(--line)", borderWidth: chosen.has(a.id) ? 2 : 1 }} onClick={() => toggle(a.id)} title={a.filename}>
                  {a.thumbnail_url || a.media_type === "image" || a.media_type === "gif" ? (
                    <img src={a.thumbnail_url ?? a.url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <span className="flex h-full items-center justify-center text-xs uppercase" style={{ color: "var(--muted)" }}>
                      {a.media_type}
                    </span>
                  )}
                  {chosen.has(a.id) && (
                    <span className="absolute top-1 right-1 rounded-full px-1.5 text-[10px]" style={{ background: "#0a0a0a", color: "#fff" }}>
                      ✓
                    </span>
                  )}
                </button>
              ))}
              {assets.length === 0 && (
                <p className="col-span-full py-6 text-center text-sm" style={{ color: "var(--muted)" }}>
                  Nothing here yet. Upload a file.
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t px-4 py-3" style={{ borderColor: "var(--line)" }}>
              <button
                className="btn btn-accent"
                disabled={chosen.size === 0}
                onClick={() => {
                  onPick(assets.filter((a) => chosen.has(a.id)).map(toRef));
                  onClose();
                }}
              >
                Add {chosen.size || ""}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex gap-2 px-4 pt-3">
              <input className="input" placeholder="Search free photos" value={uq} onChange={(e) => setUq(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchUnsplash()} autoFocus />
              <button className="btn" disabled={busy || !uq.trim()} onClick={searchUnsplash}>
                Search
              </button>
            </div>
            <div className="grid flex-1 gap-2 overflow-y-auto p-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
              {photos.map((p) => {
                const id = String(p.id);
                return (
                  <button key={id} className="relative aspect-square overflow-hidden rounded-lg border" style={{ borderColor: chosen.has(id) ? "#0a0a0a" : "var(--line)", borderWidth: chosen.has(id) ? 2 : 1 }} onClick={() => toggle(id)} title={`${p.photographer}`}>
                    <img src={String(p.thumb)} alt={String(p.alt ?? "")} className="h-full w-full object-cover" />
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between border-t px-4 py-3 text-xs" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
              <span>Photos by their creators on Unsplash.</span>
              <button className="btn btn-accent" disabled={busy || chosen.size === 0} onClick={importUnsplash}>
                Import {chosen.size || ""}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
