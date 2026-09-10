import { api } from "@/lib/studio";
import { Empty, Section, timeAgo } from "@/app/components/ui";

export const dynamic = "force-dynamic";

const STATUS_ORDER = ["scheduled", "pending_review", "pending_client", "approved", "draft", "published", "failed"];

export default async function Publish({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const posts = await api.posts(workspaceId, undefined, 100);
  const groups = STATUS_ORDER.map((s) => [s, posts.filter((p) => p.status === s)] as const).filter(([, l]) => l.length);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-bold">Publish</h1>
        <a href={`/workspace/${workspaceId}/compose/`} className="btn btn-accent">
          New post
        </a>
      </div>
      {groups.length === 0 ? (
        <Section title="Posts">
          <Empty>Nothing planned yet. Create a post or let the autopilot draft from your idea board.</Empty>
        </Section>
      ) : (
        groups.map(([status, list]) => (
          <Section key={status} title={status.replace("_", " ")} hint={`${list.length}`}>
            <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
              {list.map((p) => (
                <li key={p.id} className="flex items-start gap-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                      {p.platform_posts.map((pp) => (
                        <span key={pp.id} className="pill">
                          {pp.platform.replace("_", " ")}
                        </span>
                      ))}
                      {p.scheduled_at && <span>{new Date(p.scheduled_at).toLocaleString()}</span>}
                      {!p.scheduled_at && <span>updated {timeAgo(p.updated_at)}</span>}
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
          </Section>
        ))
      )}
    </div>
  );
}
