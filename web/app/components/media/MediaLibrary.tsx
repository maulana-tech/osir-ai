"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Empty } from "@/app/components/ui";
import { call } from "@/lib/client";
import type { Library, LibraryScope, MediaAsset } from "@/lib/types.media";
import { AssetCard } from "./AssetCard";
import { DetailPanel } from "./DetailPanel";
import { FolderTree } from "./FolderTree";

type Upload = { name: string; progress: number; status: "pending" | "done" | "error"; error?: string };

function csrf() {
  return decodeURIComponent(document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] ?? "");
}

export function MediaLibrary({ data, scope }: { data: Library; scope: LibraryScope }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [assets, setAssets] = useState(data.assets);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [open, setOpen] = useState<string | null>(params.get("open"));
  const fileInput = useRef<HTMLInputElement>(null);
  const folder = params.get("folder") ?? "";
  const type = params.get("type") ?? "";
  const starred = params.get("starred") === "1";
  const sort = params.get("sort") ?? "-date";

  useEffect(() => setAssets(data.assets), [data]);
  useEffect(() => {
    try {
      const v = localStorage.getItem("media-view");
      if (v === "list" || v === "grid") setView(v);
    } catch {
      /* no storage */
    }
  }, []);

  // Poll assets that are still being processed so thumbnails appear without a reload.
  useEffect(() => {
    const busy = assets.filter((a) => a.processing_status === "pending" || a.processing_status === "processing");
    if (busy.length === 0) return;
    const t = setInterval(() => {
      for (const a of busy) {
        call<MediaAsset>(`${scope.apiBase}/${a.id}/status`)
          .then((fresh) => setAssets((list) => list.map((x) => (x.id === fresh.id ? fresh : x))))
          .catch(() => {});
      }
    }, 3000);
    return () => clearInterval(t);
  }, [assets, scope.apiBase]);

  function navigate(patch: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    next.delete("page");
    next.delete("open");
    router.push(`${pathname}?${next}`);
  }

  function pageHref(page: number) {
    const next = new URLSearchParams(params.toString());
    next.set("page", String(page));
    return `${pathname}?${next}`;
  }

  function startUpload(list: FileList | File[] | null) {
    let files = Array.from(list ?? []);
    if (!files.length) return;
    if (files.length > data.max_bulk_upload) files = files.slice(0, data.max_bulk_upload);
    const queue: Upload[] = files.map((f) => ({ name: f.name, progress: 0, status: "pending" }));
    setUploads(queue);
    let done = 0;
    files.forEach((file, i) => {
      const fd = new FormData();
      fd.append("files", file);
      if (folder && !scope.shared) fd.append("folder_id", folder);
      const xhr = new XMLHttpRequest();
      const patch = (p: Partial<Upload>) => setUploads((u) => u.map((x, j) => (j === i ? { ...x, ...p } : x)));
      xhr.upload.addEventListener("progress", (e) => e.lengthComputable && patch({ progress: Math.round((e.loaded / e.total) * 100) }));
      const finish = () => {
        if (++done === files.length) {
          setTimeout(() => setUploads([]), 1500);
          router.refresh();
        }
      };
      xhr.addEventListener("load", () => {
        let error: string | undefined;
        try {
          const body = JSON.parse(xhr.responseText);
          const r = body.results?.[0];
          if (xhr.status >= 300) error = body.detail ?? "Upload failed";
          else if (r && !r.ok) error = r.error;
        } catch {
          error = xhr.status >= 300 ? "Upload failed" : undefined;
        }
        patch(error ? { status: "error", error } : { status: "done", progress: 100 });
        finish();
      });
      xhr.addEventListener("error", () => {
        patch({ status: "error", error: "Network error" });
        finish();
      });
      xhr.open("POST", `${scope.apiBase}/upload`);
      xhr.setRequestHeader("X-CSRFToken", csrf());
      xhr.send(fd);
    });
  }

  const pill = (active: boolean) => `pill cursor-pointer ${active ? "pill-accent" : ""}`;

  return (
    <div
      className="flex gap-6"
      onDragOver={(e) => {
        if (scope.canUpload) {
          e.preventDefault();
          setDragOver(true);
        }
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        if (!scope.canUpload) return;
        e.preventDefault();
        setDragOver(false);
        startUpload(e.dataTransfer.files);
      }}
    >
      {!scope.shared && data.folders && (
        <aside className="w-52 shrink-0">
          <FolderTree folders={data.folders} current={folder} starred={starred} scope={scope} onSelect={(id) => navigate({ folder: id, starred: null })} onStarred={() => navigate({ folder: null, starred: starred ? null : "1" })} />
        </aside>
      )}

      <div className="min-w-0 flex-1">
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <input
            className="input w-56"
            type="search"
            placeholder="Search files and tags"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && navigate({ q: q.trim() || null })}
          />
          <span className={pill(!type)} onClick={() => navigate({ type: null })}>
            All
          </span>
          {data.file_types.map((t) => (
            <span key={t.value} className={pill(type === t.value)} onClick={() => navigate({ type: t.value })}>
              {t.label}
            </span>
          ))}
          <select className="input w-auto" value={sort} onChange={(e) => navigate({ sort: e.target.value })}>
            <option value="-date">Newest first</option>
            <option value="date">Oldest first</option>
            <option value="name">Name A–Z</option>
            <option value="-name">Name Z–A</option>
            <option value="-size">Largest first</option>
            <option value="size">Smallest first</option>
          </select>
          <span className="ml-auto flex items-center gap-1">
            {(["grid", "list"] as const).map((v) => (
              <button
                key={v}
                className={`btn ${view === v ? "btn-accent" : ""}`}
                onClick={() => {
                  setView(v);
                  try {
                    localStorage.setItem("media-view", v);
                  } catch {
                    /* no storage */
                  }
                }}
              >
                {v}
              </button>
            ))}
            {scope.canUpload && (
              <>
                <button className="btn btn-accent" onClick={() => fileInput.current?.click()}>
                  Upload
                </button>
                <input ref={fileInput} type="file" multiple accept={data.accepted_file_types} className="hidden" onChange={(e) => startUpload(e.target.files)} />
              </>
            )}
          </span>
        </div>

        {uploads.length > 0 && (
          <ul className="panel mb-4 divide-y p-3 text-xs" style={{ borderColor: "var(--line)" }}>
            {uploads.map((u, i) => (
              <li key={i} className="flex items-center gap-3 py-1">
                <span className="w-48 truncate">{u.name}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--line)" }}>
                  <span className="block h-full" style={{ width: `${u.progress}%`, background: u.status === "error" ? "var(--bad)" : "#0a0a0a" }} />
                </span>
                <span style={{ color: u.status === "error" ? "var(--bad)" : "var(--muted)" }}>{u.status === "error" ? u.error : u.status === "done" ? "done" : `${u.progress}%`}</span>
              </li>
            ))}
          </ul>
        )}

        {dragOver && (
          <div className="mb-4 rounded-lg border-2 border-dashed p-6 text-center text-sm" style={{ borderColor: "#0a0a0a" }}>
            Drop to upload
          </div>
        )}

        {assets.length === 0 ? (
          <Empty>{q || type || folder || starred ? "Nothing matches these filters." : scope.canUpload ? "No media yet. Upload files or drop them here." : "No media yet."}</Empty>
        ) : view === "grid" ? (
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))" }}>
            {assets.map((a) => (
              <AssetCard key={a.id} asset={a} scope={scope} onOpen={() => setOpen(a.id)} onChange={(fresh) => setAssets((l) => l.map((x) => (x.id === fresh.id ? fresh : x)))} />
            ))}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs" style={{ color: "var(--muted)" }}>
                <th className="py-1 font-medium">Name</th>
                <th className="py-1 font-medium">Type</th>
                <th className="py-1 font-medium">Size</th>
                <th className="py-1 font-medium">Dimensions</th>
                <th className="py-1 font-medium">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id} className="cursor-pointer border-t hover:bg-neutral-50" style={{ borderColor: "var(--line)" }} onClick={() => setOpen(a.id)}>
                  <td className="py-2 pr-3">
                    <span className="flex items-center gap-2">
                      {a.is_starred && <span title="Starred">★</span>}
                      <span className="truncate">{a.filename}</span>
                      {a.is_shared && <span className="pill">shared</span>}
                    </span>
                  </td>
                  <td className="py-2 pr-3 uppercase" style={{ color: "var(--muted)" }}>
                    {a.media_type}
                  </td>
                  <td className="py-2 pr-3">{a.file_size_display}</td>
                  <td className="py-2 pr-3">{a.width && a.height ? `${a.width}×${a.height}` : a.duration ? `${Math.round(a.duration)}s` : ""}</td>
                  <td className="py-2" style={{ color: "var(--muted)" }}>
                    {new Date(a.created_at).toLocaleDateString()}
                    {a.uploaded_by && ` · ${a.uploaded_by}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {data.num_pages > 1 && (
          <div className="mt-4 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
            <span>
              Page {data.page} of {data.num_pages} · {data.total} files
            </span>
            <span className="flex gap-3">
              {data.page > 1 && (
                <Link href={pageHref(data.page - 1)} className="underline">
                  Previous
                </Link>
              )}
              {data.page < data.num_pages && (
                <Link href={pageHref(data.page + 1)} className="underline">
                  Next
                </Link>
              )}
            </span>
          </div>
        )}
      </div>

      {open && (
        <DetailPanel
          id={open}
          scope={scope}
          folders={data.folders ?? []}
          onClose={() => setOpen(null)}
          onChange={(fresh) => setAssets((l) => l.map((x) => (x.id === fresh.id ? fresh : x)))}
          onDeleted={() => {
            setOpen(null);
            router.refresh();
          }}
        />
      )}
    </div>
  );
}
