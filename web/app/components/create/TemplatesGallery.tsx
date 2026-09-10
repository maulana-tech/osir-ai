"use client";

import Link from "next/link";
import { useState } from "react";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Templates } from "@/lib/types.composer";

export function TemplatesGallery({ workspaceId, data }: { workspaceId: string; data: Templates }) {
  const { run, busy, Feedback } = useAction();
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");
  const shown = data.builtin.filter((t) => (cat === "all" || t.category === cat) && (!q.trim() || `${t.title} ${t.description} ${t.body ?? ""}`.toLowerCase().includes(q.toLowerCase())));
  const featured = data.builtin.filter((t) => data.featured_ids.includes(t.id));
  return (
    <div className="space-y-6">
      {data.saved.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Your templates
          </h3>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.saved.map((t) => (
              <li key={t.id} className="rounded-lg border p-3 text-sm" style={{ borderColor: "var(--line)" }}>
                <div className="font-semibold">{t.name}</div>
                {t.description && (
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    {t.description}
                  </p>
                )}
                <p className="mt-1 line-clamp-2 text-xs">{String(t.template_data.caption ?? "")}</p>
                <div className="mt-2 flex gap-2 text-xs">
                  <Link href={`/w/${workspaceId}/compose?template=${t.id}`} className="btn">
                    Use
                  </Link>
                  <button className="btn btn-bad" disabled={busy} onClick={() => window.confirm(`Delete template "${t.name}"?`) && run(() => call(`/api/web/workspaces/${workspaceId}/composer/templates/${t.id}`, { method: "DELETE" }))}>
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <Feedback />
        </div>
      )}
      {cat === "all" && !q && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Featured
          </h3>
          <ul className="grid gap-2 sm:grid-cols-3">
            {featured.map((t) => (
              <li key={t.id} className="rounded-lg border p-3 text-sm" style={{ borderColor: "#0a0a0a" }}>
                <div className="font-semibold">
                  {t.emoji} {t.title}
                </div>
                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  {t.description}
                </p>
                <Link href={`/w/${workspaceId}/compose?template=${t.id}`} className="btn mt-2">
                  Use
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {data.categories.map((c) => (
            <button key={c.slug} className={`pill cursor-pointer ${cat === c.slug ? "pill-accent" : ""}`} onClick={() => setCat(c.slug)}>
              {c.label}
            </button>
          ))}
          <input className="input ml-auto w-56" type="search" placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((t) => (
            <li key={t.id} className="flex flex-col rounded-lg border p-3 text-sm" style={{ borderColor: "var(--line)" }}>
              <div className="font-semibold">
                {t.emoji} {t.title}
              </div>
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                {t.description}
              </p>
              {t.body && <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-xs">{t.body}</p>}
              <div className="mt-auto pt-2">
                <Link href={`/w/${workspaceId}/compose?template=${t.id}`} className="btn">
                  Use
                </Link>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
