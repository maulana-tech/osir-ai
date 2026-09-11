"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { LibraryScope, MediaAsset } from "@/lib/types.media";

type Rect = { x: number; y: number; w: number; h: number };

/**
 * Crop is drawn on the original image; rotate and flip are applied by the
 * server after the crop (same order as the processing task), so the preview
 * strip shows them as a CSS transform of the selection.
 */
function ImageEditor({ asset, scope }: { asset: MediaAsset; scope: LibraryScope }) {
  const router = useRouter();
  const { run, busy, Feedback } = useAction();
  const img = useRef<HTMLImageElement>(null);
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<Rect | null>(null); // displayed px
  const [rotate, setRotate] = useState(0);
  const [flip, setFlip] = useState<"" | "horizontal" | "vertical">("");
  const [scale, setScale] = useState(1); // natural px per displayed px

  const point = (e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: Math.min(Math.max(e.clientX - r.left, 0), r.width), y: Math.min(Math.max(e.clientY - r.top, 0), r.height) };
  };
  const natural = rect ? { x: Math.round(rect.x * scale), y: Math.round(rect.y * scale), width: Math.round(rect.w * scale), height: Math.round(rect.h * scale) } : null;
  const dirty = !!(natural && natural.width > 0 && natural.height > 0) || rotate !== 0 || flip !== "";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
      <div className="panel p-3">
        <div
          className="relative inline-block max-w-full touch-none select-none"
          style={{ cursor: "crosshair" }}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            const p = point(e);
            setDrag(p);
            setRect({ x: p.x, y: p.y, w: 0, h: 0 });
          }}
          onPointerMove={(e) => {
            if (!drag) return;
            const p = point(e);
            setRect({ x: Math.min(drag.x, p.x), y: Math.min(drag.y, p.y), w: Math.abs(p.x - drag.x), h: Math.abs(p.y - drag.y) });
          }}
          onPointerUp={() => setDrag(null)}
        >
          <img
            ref={img}
            src={asset.url}
            alt=""
            draggable={false}
            className="block max-h-[70vh] max-w-full"
            onLoad={(e) => setScale(e.currentTarget.naturalWidth / e.currentTarget.clientWidth)}
          />
          {rect && rect.w > 0 && rect.h > 0 && (
            <div className="pointer-events-none absolute border-2" style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h, borderColor: "#fff", boxShadow: "0 0 0 9999px rgba(0,0,0,0.45)" }} />
          )}
        </div>
        <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
          Drag on the image to select a crop. {asset.width}×{asset.height}px original.
        </p>
      </div>

      <div className="space-y-4">
        <Section title="Adjustments">
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <button className="btn" onClick={() => setRotate((r) => (r + 270) % 360)}>
                ⟲ 90°
              </button>
              <button className="btn" onClick={() => setRotate((r) => (r + 90) % 360)}>
                ⟳ 90°
              </button>
              <button className={`btn ${flip === "horizontal" ? "btn-accent" : ""}`} onClick={() => setFlip((f) => (f === "horizontal" ? "" : "horizontal"))}>
                Flip ↔
              </button>
              <button className={`btn ${flip === "vertical" ? "btn-accent" : ""}`} onClick={() => setFlip((f) => (f === "vertical" ? "" : "vertical"))}>
                Flip ↕
              </button>
              {rect && (
                <button className="btn" onClick={() => setRect(null)}>
                  Clear crop
                </button>
              )}
            </div>
            <dl className="grid grid-cols-2 gap-1 text-xs">
              <dt style={{ color: "var(--muted)" }}>Crop</dt>
              <dd>{natural && natural.width > 0 ? `${natural.width}×${natural.height} at ${natural.x},${natural.y}` : "none"}</dd>
              <dt style={{ color: "var(--muted)" }}>Rotate</dt>
              <dd>{rotate}°</dd>
              <dt style={{ color: "var(--muted)" }}>Flip</dt>
              <dd>{flip || "none"}</dd>
            </dl>
            <div className="overflow-hidden rounded-lg" style={{ background: "#f5f5f5" }}>
              <div className="flex h-40 items-center justify-center">
                <img src={asset.url} alt="" className="max-h-36 max-w-full" style={{ transform: `rotate(${rotate}deg) scaleX(${flip === "horizontal" ? -1 : 1}) scaleY(${flip === "vertical" ? -1 : 1})` }} />
              </div>
            </div>
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Saving creates a new version; the original stays in the history.
            </p>
          </div>
        </Section>
        <div className="flex justify-end gap-2">
          <Link href={`${scope.pageBase}?open=${asset.id}`} className="btn">
            Cancel
          </Link>
          <button
            className="btn btn-accent"
            disabled={busy || !dirty}
            onClick={async () => {
              const body: Record<string, number | string> = {};
              if (natural && natural.width > 0 && natural.height > 0) Object.assign(body, { crop_x: natural.x, crop_y: natural.y, crop_width: natural.width, crop_height: natural.height });
              if (rotate) body.rotate = rotate;
              if (flip) body.flip = flip;
              const r = await run(() => call(`${scope.apiBase}/${asset.id}/edit`, { method: "POST", body: JSON.stringify(body) }));
              if (r !== undefined) router.push(`${scope.pageBase}?open=${asset.id}`);
            }}
          >
            Save
          </button>
        </div>
        <Feedback />
      </div>
    </div>
  );
}

function VideoEditor({ asset, scope }: { asset: MediaAsset; scope: LibraryScope }) {
  const router = useRouter();
  const { run, busy, Feedback } = useAction();
  const video = useRef<HTMLVideoElement>(null);
  const [len, setLen] = useState(asset.duration || 0);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(asset.duration || 0);

  function preview() {
    const v = video.current;
    if (!v) return;
    v.currentTime = start;
    v.play();
    const stop = () => {
      if (v.currentTime >= end) {
        v.pause();
        v.removeEventListener("timeupdate", stop);
      }
    };
    v.addEventListener("timeupdate", stop);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
      <div className="panel p-3">
        <video
          ref={video}
          src={asset.url}
          controls
          preload="metadata"
          className="max-h-[70vh] w-full"
          onLoadedMetadata={(e) => {
            setLen(e.currentTarget.duration);
            if (!end) setEnd(e.currentTarget.duration);
          }}
        />
      </div>
      <div className="space-y-4">
        <Section title="Trim">
          <div className="space-y-3 text-sm">
            <label className="block">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                Start (s)
              </span>
              <input className="input" type="number" min={0} max={end} step={0.1} value={start} onChange={(e) => setStart(Math.max(0, Math.min(Number(e.target.value), end)))} />
            </label>
            <label className="block">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                End (s)
              </span>
              <input className="input" type="number" min={start} max={len || undefined} step={0.1} value={end} onChange={(e) => setEnd(Math.max(start, Math.min(Number(e.target.value), len || Infinity)))} />
            </label>
            <div className="flex gap-2">
              <button className="btn" onClick={() => setStart(video.current?.currentTime ?? 0)}>
                Start = now
              </button>
              <button className="btn" onClick={() => setEnd(video.current?.currentTime ?? end)}>
                End = now
              </button>
              <button className="btn" onClick={preview}>
                Preview
              </button>
            </div>
            <p className="text-xs" style={{ color: "var(--muted)" }}>
              Keeps {(end - start).toFixed(1)}s of {len.toFixed(1)}s. Saving creates a new version.
            </p>
          </div>
        </Section>
        <div className="flex justify-end gap-2">
          <Link href={`${scope.pageBase}?open=${asset.id}`} className="btn">
            Cancel
          </Link>
          <button
            className="btn btn-accent"
            disabled={busy || end <= start}
            onClick={async () => {
              const r = await run(() => call(`${scope.apiBase}/${asset.id}/edit`, { method: "POST", body: JSON.stringify({ trim_start: start, trim_end: end }) }));
              if (r !== undefined) router.push(`${scope.pageBase}?open=${asset.id}`);
            }}
          >
            Save trim
          </button>
        </div>
        <Feedback />
      </div>
    </div>
  );
}

export function AssetEditor({ asset, scope }: { asset: MediaAsset; scope: LibraryScope }) {
  if (asset.media_type === "video") return <VideoEditor asset={asset} scope={scope} />;
  if (asset.media_type === "image" || asset.media_type === "gif") return <ImageEditor asset={asset} scope={scope} />;
  return (
    <p className="text-sm" style={{ color: "var(--muted)" }}>
      This file type cannot be edited here.
    </p>
  );
}
