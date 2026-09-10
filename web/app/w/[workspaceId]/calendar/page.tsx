import Link from "next/link";
import { CalendarBoard } from "@/app/components/calendar/CalendarBoard";
import { Empty, PageHeader, Section, timeAgo } from "@/app/components/ui";
import { windowFor } from "@/lib/calendar";
import { api } from "@/lib/studio";
import type { Post } from "@/lib/types";

export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

function list(v: string | string[] | undefined): string[] {
  return v === undefined ? [] : Array.isArray(v) ? v : [v];
}

const TABS: { key: string; label: string; statuses: string[] }[] = [
  { key: "queue", label: "Queue", statuses: ["scheduled", "approved"] },
  { key: "drafts", label: "Drafts", statuses: ["draft", "changes_requested", "rejected"] },
  { key: "approvals", label: "Approvals", statuses: ["pending_review", "pending_client", "on_hold"] },
  { key: "sent", label: "Sent", statuses: ["published", "failed", "publishing"] },
];

export default async function Publish({ params, searchParams }: { params: Promise<{ workspaceId: string }>; searchParams: Promise<Search> }) {
  const { workspaceId } = await params;
  const q = await searchParams;
  const view = typeof q.view === "string" ? q.view : "month";
  const today = new Date().toISOString().slice(0, 10);
  const date = typeof q.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : today;
  const tz = typeof q.tz === "string" ? q.tz : undefined;
  const channels = list(q.channel);
  const statuses = list(q.status);

  if (view === "list") {
    const tab = TABS.find((t) => t.key === q.tab) ?? TABS[0];
    const groups = await Promise.all(tab.statuses.map((s) => api.posts(workspaceId, s, 100)));
    const seen = new Set<string>();
    const posts: Post[] = [];
    for (const g of groups) for (const p of g) if (!seen.has(p.id)) (seen.add(p.id), posts.push(p));
    posts.sort((a, b) => (b.scheduled_at ?? b.updated_at).localeCompare(a.scheduled_at ?? a.updated_at));
    return (
      <div>
        <PageHeader title="Publish">
          <div className="flex items-center gap-2">
            <Link className="btn" href={`/w/${workspaceId}/calendar`}>
              calendar
            </Link>
            <a href={`/workspace/${workspaceId}/compose/`} className="btn btn-accent">
              New post
            </a>
          </div>
        </PageHeader>
        <div className="mb-4 flex gap-1 text-xs">
          {TABS.map((t) => (
            <Link key={t.key} className="btn" style={t.key === tab.key ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined} href={`/w/${workspaceId}/calendar?view=list&tab=${t.key}`}>
              {t.label}
            </Link>
          ))}
        </div>
        <Section title={tab.label} hint={`${posts.length}`}>
          {posts.length === 0 ? (
            <Empty>Nothing here.</Empty>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
              {posts.map((p) => (
                <li key={p.id} className="flex items-start gap-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                      {p.platform_posts.map((pp) => (
                        <span key={pp.id} className="pill">
                          {pp.platform.replace("_", " ")} · {pp.status.replace("_", " ")}
                        </span>
                      ))}
                      {p.scheduled_at ? <span>{new Date(p.scheduled_at).toLocaleString()}</span> : <span>updated {timeAgo(p.updated_at)}</span>}
                    </div>
                    {p.title && <div className="mt-1 text-sm font-semibold">{p.title}</div>}
                    <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-sm">{p.caption}</p>
                  </div>
                  <a href={`/workspace/${workspaceId}/compose/${p.id}/`} className="btn shrink-0">
                    Open
                  </a>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    );
  }

  const v = view === "week" || view === "day" ? view : "month";
  const { start, end } = windowFor(v, date);
  const data = await api.calendar(workspaceId, { start, end, tz, channel: channels, status: statuses });
  return (
    <div>
      <PageHeader title="Publish">
        <a href={`/workspace/${workspaceId}/compose/`} className="btn btn-accent">
          New post
        </a>
      </PageHeader>
      <CalendarBoard workspaceId={workspaceId} view={v} date={date} data={data} channels={channels} statuses={statuses} />
    </div>
  );
}
