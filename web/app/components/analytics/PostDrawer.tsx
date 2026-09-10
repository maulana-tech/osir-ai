"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { call } from "@/lib/client";
import type { PostDetail } from "@/lib/types.analytics";
import { Sparkline } from "./Sparkline";

function fmt(value: number, kind: string) {
  if (kind === "percent") return `${value.toFixed(2)}%`;
  if (kind === "minutes") return `${Math.round(value)} min`;
  return Math.round(value).toLocaleString();
}

/** Slide-over with one post's metrics; opened with ?post=<platform_post_id>. */
export function PostDrawer({ workspaceId, postId, closeHref }: { workspaceId: string; postId: string; closeHref: string }) {
  const router = useRouter();
  const [d, setD] = useState<PostDetail | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    call<PostDetail>(`/api/web/workspaces/${workspaceId}/analytics/posts/${postId}`)
      .then(setD)
      .catch((e) => setErr(e.message));
  }, [workspaceId, postId]);
  const close = () => router.push(closeHref);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="fixed inset-y-0 right-0 z-20 flex w-full max-w-md flex-col overflow-y-auto border-l bg-white shadow-xl" style={{ borderColor: "var(--line)" }} role="dialog">
      <div className="flex items-center gap-3 border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
        {d?.account.avatar_url ? <img src={d.account.avatar_url} alt="" className="h-8 w-8 rounded-full" /> : <span className="h-8 w-8 rounded-full" style={{ background: "#e5e5e5" }} />}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{d?.account.name ?? "…"}</div>
          {d?.account.handle && (
            <div className="text-xs" style={{ color: "var(--muted)" }}>
              @{d.account.handle.replace(/^@/, "")}
            </div>
          )}
        </div>
        <button className="btn" onClick={close}>
          Close
        </button>
      </div>
      {err && (
        <p className="px-4 pt-3 text-xs" style={{ color: "var(--bad)" }}>
          {err}
        </p>
      )}
      {d && (
        <div className="space-y-4 p-4 text-sm">
          <div className="relative overflow-hidden rounded-lg" style={{ background: "#f5f5f5", height: 240 }}>
            {d.media_preview?.kind === "video" ? <video src={d.media_preview.url} controls muted preload="metadata" className="h-full w-full object-cover" /> : d.media_preview ? <img src={d.media_preview.url} alt="" className="h-full w-full object-cover" /> : null}
            <span className="absolute top-2 left-2 rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: "rgba(0,0,0,0.7)", color: "#fff" }}>
              {d.media_kind}
            </span>
          </div>
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Post copy
            </div>
            <p className="whitespace-pre-wrap">{d.caption || "(no caption)"}</p>
            <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
              Published {d.date}
              {d.days_ago !== null && ` · ${d.days_ago}d ago`}
              {d.captured_at && ` · metrics captured ${new Date(d.captured_at).toLocaleDateString()}`}
            </p>
          </div>
          <div>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Performance
            </div>
            <div className="grid grid-cols-2 gap-2">
              {d.metric_tiles.map((t) => (
                <div key={t.key} className="rounded-lg border p-3" style={{ borderColor: t.is_primary ? "#0a0a0a" : "var(--line)" }}>
                  <div className="text-[11px]" style={{ color: "var(--muted)" }}>
                    {t.label}
                  </div>
                  <div className="text-lg font-semibold">{fmt(t.value, t.kind)}</div>
                  {t.sparkline.length > 1 && <Sparkline series={t.sparkline} width={140} height={24} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
