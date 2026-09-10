"use client";

import type { ComposerAccount, MediaRef } from "@/lib/types.composer";

/** Caption length as the platform counts it: each escaped character costs two. */
export function wireLength(text: string, escaped: string): number {
  let n = text.length;
  if (escaped) for (const ch of text) if (escaped.includes(ch)) n += 1;
  return n;
}

export function PreviewCard({ account, title, caption, firstComment, media }: { account: ComposerAccount; title: string; caption: string; firstComment: string; media: MediaRef[] }) {
  const n = wireLength(caption, account.escaped_chars);
  const over = n > account.char_limit;
  const shown = over ? caption.slice(0, account.char_limit) : caption;
  return (
    <div className="rounded-lg border text-sm" style={{ borderColor: over ? "var(--bad)" : "var(--line)" }}>
      <div className="flex items-center gap-2 px-3 py-2">
        {account.avatar_url ? <img src={account.avatar_url} alt="" className="h-7 w-7 rounded-full" /> : <span className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-bold uppercase" style={{ background: "#0a0a0a", color: "#fff" }}>{account.platform.slice(0, 2)}</span>}
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold">{account.name}</div>
          <div className="text-[10px] uppercase" style={{ color: "var(--muted)" }}>
            {account.platform.replace("_", " ")}
          </div>
        </div>
        <span className="ml-auto text-[10px]" style={{ color: over ? "var(--bad)" : "var(--muted)" }}>
          {n}/{account.char_limit}
        </span>
      </div>
      {media.length > 0 && (
        <div className="grid gap-0.5" style={{ gridTemplateColumns: media.length > 1 ? "1fr 1fr" : "1fr" }}>
          {media.slice(0, 4).map((m) => (
            <div key={m.id} className="aspect-square overflow-hidden" style={{ background: "#f5f5f5" }}>
              {m.media_type === "video" ? <video src={m.url} className="h-full w-full object-cover" muted /> : <img src={m.thumbnail_url ?? m.url} alt="" className="h-full w-full object-cover" />}
            </div>
          ))}
        </div>
      )}
      <div className="px-3 py-2">
        {account.needs_title && title && <div className="mb-1 font-semibold">{title}</div>}
        <p className="whitespace-pre-wrap text-xs">
          {shown || <span style={{ color: "var(--muted)" }}>Your caption will appear here.</span>}
          {over && <span style={{ color: "var(--bad)" }}>…</span>}
        </p>
        {firstComment && account.supports_first_comment && (
          <p className="mt-2 border-t pt-2 text-[11px]" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
            First comment: {firstComment}
          </p>
        )}
      </div>
    </div>
  );
}
