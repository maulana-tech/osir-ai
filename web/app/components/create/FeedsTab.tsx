"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Empty, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Explore, FeedEvent, FeedsData } from "@/lib/types.composer";

export function FeedsTab({ workspaceId, data }: { workspaceId: string; data: FeedsData }) {
  const router = useRouter();
  const { run, busy, Feedback } = useAction();
  const [events, setEvents] = useState<FeedEvent[]>(data.events);
  const [nextOffset, setNextOffset] = useState(data.next_offset);
  const [hasMore, setHasMore] = useState(data.has_more);
  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");
  const [explore, setExplore] = useState<Explore | null>(null);
  const base = `/api/web/workspaces/${workspaceId}/composer/feeds`;

  const select = (id: string) => router.push(`/w/${workspaceId}/create?tab=feeds${id !== "all" ? `&feed_id=${id}` : ""}`);

  async function loadMore() {
    const r = await call<FeedsData>(`${base}?feed_id=${data.selected_feed_id}&offset=${nextOffset}`);
    setEvents((e) => [...e, ...r.events]);
    setNextOffset(r.next_offset);
    setHasMore(r.has_more);
  }

  async function openExplore(category = "osir-favorites") {
    setExplore(await call<Explore>(`${base}/explore?category=${category}`));
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      <aside className="text-sm">
        <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
          <span>Feeds</span>
          <span className="flex gap-2">
            <button className="underline" onClick={() => openExplore()}>
              explore
            </button>
            <button className="underline" onClick={() => setAdding(true)}>
              add
            </button>
          </span>
        </div>
        <ul className="space-y-0.5">
          <li>
            <button className="w-full rounded-md px-2 py-1 text-left text-xs hover:bg-neutral-100" style={data.selected_feed_id === "all" ? { background: "#0a0a0a", color: "#fff" } : undefined} onClick={() => select("all")}>
              All feeds
            </button>
          </li>
          {data.feeds.map((f) => (
            <li key={f.id} className="group flex items-center gap-1">
              <button className="min-w-0 flex-1 truncate rounded-md px-2 py-1 text-left text-xs hover:bg-neutral-100" style={data.selected_feed_id === f.id ? { background: "#0a0a0a", color: "#fff" } : undefined} onClick={() => select(f.id)} title={f.url}>
                {f.favicon_url && <img src={f.favicon_url} alt="" className="mr-1 inline h-3 w-3" />}
                {f.name}
              </button>
              <button className="hidden text-xs group-hover:inline" title="Unsubscribe" disabled={busy} onClick={() => window.confirm(`Unsubscribe from ${f.name}?`) && run(() => call(`${base}/${f.id}`, { method: "DELETE" }))}>
                ×
              </button>
            </li>
          ))}
        </ul>
        {adding && (
          <div className="mt-3 space-y-1">
            <input className="input text-xs" placeholder="https://example.com/feed.xml" value={url} autoFocus onChange={(e) => setUrl(e.target.value)} />
            <div className="flex gap-1">
              <button
                className="btn btn-accent"
                disabled={busy || !url.trim()}
                onClick={async () => {
                  const r = await run(() => call(base, { method: "POST", body: JSON.stringify({ rss_url: url }) }), "Subscribed");
                  if (r !== undefined) {
                    setAdding(false);
                    setUrl("");
                  }
                }}
              >
                Subscribe
              </button>
              <button className="btn" onClick={() => setAdding(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}
        <Feedback />
        {data.last_refreshed_at && (
          <p className="mt-3 text-[11px]" style={{ color: "var(--muted)" }}>
            Refreshed {timeAgo(data.last_refreshed_at)} · {data.total} items
          </p>
        )}
      </aside>

      <div>
        {data.feeds.length === 0 ? (
          <Empty>
            No feeds yet. Subscribe to blogs and news you want to react to, or{" "}
            <button className="underline" onClick={() => openExplore()}>
              explore curated feeds
            </button>
            .
          </Empty>
        ) : events.length === 0 ? (
          <Empty>Nothing fetched yet. Feeds refresh every 10 minutes.</Empty>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {events.map((e) => (
              <li key={`${e.feed_id}:${e.event_id}`} className="flex gap-3 py-3 text-sm">
                {e.image_url && <img src={e.image_url} alt="" className="h-20 w-28 shrink-0 rounded object-cover" style={{ background: "#f5f5f5" }} />}
                <div className="min-w-0 flex-1">
                  <div className="text-xs" style={{ color: "var(--muted)" }}>
                    {e.feed_name}
                    {e.published_at && ` · ${timeAgo(e.published_at)}`}
                  </div>
                  <a href={e.link} target="_blank" rel="noreferrer" className="font-semibold hover:underline">
                    {e.title}
                  </a>
                  {e.summary && (
                    <p className="line-clamp-2 text-xs" style={{ color: "var(--muted)" }}>
                      {e.summary}
                    </p>
                  )}
                  <div className="mt-1 text-xs">
                    <Link href={`/w/${workspaceId}/compose?prefill=${encodeURIComponent(`${e.title}\n${e.link}`)}`} className="underline">
                      Write a post about this
                    </Link>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        {hasMore && (
          <div className="mt-3 text-center">
            <button className="btn" onClick={loadMore}>
              Load more
            </button>
          </div>
        )}
      </div>

      {explore && (
        <div className="fixed inset-0 z-30 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }} onClick={() => setExplore(null)}>
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()} role="dialog">
            <div className="flex flex-wrap items-center gap-1 border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
              {explore.categories.map((c) => (
                <button key={c.slug} className={`pill cursor-pointer ${explore.active_category === c.slug ? "pill-accent" : ""}`} onClick={() => openExplore(c.slug)}>
                  {c.label}
                </button>
              ))}
              <button className="btn ml-auto" onClick={() => setExplore(null)}>
                Close
              </button>
            </div>
            <ul className="flex-1 divide-y overflow-y-auto px-4" style={{ borderColor: "var(--line)" }}>
              {explore.curated_feeds.map((f) => (
                <li key={f.rss} className="flex items-center gap-3 py-2 text-sm">
                  {f.favicon && <img src={f.favicon} alt="" className="h-5 w-5 rounded" />}
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold">{f.name}</div>
                    <div className="truncate text-xs" style={{ color: "var(--muted)" }}>
                      {f.description || f.website}
                    </div>
                  </div>
                  {f.subscribed ? (
                    <span className="pill pill-ok">subscribed</span>
                  ) : (
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={async () => {
                        await run(() => call(base, { method: "POST", body: JSON.stringify({ rss_url: f.rss, name: f.name, website_url: f.website, source: "explore" }) }));
                        openExplore(explore.active_category);
                      }}
                    >
                      Subscribe
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
