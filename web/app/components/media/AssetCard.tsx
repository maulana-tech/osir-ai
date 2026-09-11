"use client";

import { call } from "@/lib/client";
import type { LibraryScope, MediaAsset } from "@/lib/types.media";

export function Thumb({ asset, className }: { asset: MediaAsset; className?: string }) {
  const src = asset.thumbnail_url ?? ((asset.media_type === "image" || asset.media_type === "gif") && asset.processing_status !== "failed" ? asset.url : null);
  if (src) return <img src={src} alt={asset.alt_text || asset.filename} className={`h-full w-full object-cover ${className ?? ""}`} loading="lazy" />;
  const busy = asset.processing_status === "pending" || asset.processing_status === "processing";
  return (
    <div className={`flex h-full w-full items-center justify-center text-xs uppercase ${className ?? ""}`} style={{ background: "#f5f5f5", color: "var(--muted)" }}>
      {busy ? "processing…" : asset.media_type}
    </div>
  );
}

export function duration(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function AssetCard({ asset, scope, onOpen, onChange }: { asset: MediaAsset; scope: LibraryScope; onOpen: () => void; onChange: (a: MediaAsset) => void }) {
  return (
    <div className="group cursor-pointer overflow-hidden rounded-lg border" style={{ borderColor: "var(--line)" }} onClick={onOpen}>
      <div className="relative aspect-square overflow-hidden">
        <Thumb asset={asset} />
        <span className="absolute top-2 left-2 rounded px-1.5 text-[10px] font-semibold uppercase" style={{ background: "rgba(255,255,255,0.9)" }}>
          {asset.media_type}
        </span>
        {asset.is_shared && (
          <span className="absolute top-2 right-2 rounded px-1.5 text-[10px] font-semibold uppercase" style={{ background: "#0a0a0a", color: "#fff" }}>
            shared
          </span>
        )}
        {asset.media_type === "video" && asset.duration > 0 && (
          <span className="absolute bottom-2 left-2 rounded px-1.5 text-[10px] font-semibold" style={{ background: "rgba(0,0,0,0.7)", color: "#fff" }}>
            {duration(asset.duration)}
          </span>
        )}
        {scope.canUpload && !asset.is_shared && (
          <button
            className="absolute right-2 bottom-2 flex h-7 w-7 items-center justify-center rounded-full text-sm"
            style={{ background: "rgba(255,255,255,0.9)", opacity: asset.is_starred ? 1 : undefined }}
            title={asset.is_starred ? "Unstar" : "Star"}
            onClick={(e) => {
              e.stopPropagation();
              call<{ is_starred: boolean }>(`${scope.apiBase}/${asset.id}/star`, { method: "POST" })
                .then((r) => onChange({ ...asset, is_starred: r.is_starred }))
                .catch(() => {});
            }}
          >
            {asset.is_starred ? "★" : "☆"}
          </button>
        )}
      </div>
      <div className="px-3 py-2">
        <p className="truncate text-xs font-medium">{asset.filename}</p>
        <p className="text-[11px]" style={{ color: "var(--muted)" }}>
          {asset.file_size_display}
          {asset.width > 0 && asset.height > 0 && ` · ${asset.width}×${asset.height}`}
        </p>
      </div>
    </div>
  );
}
