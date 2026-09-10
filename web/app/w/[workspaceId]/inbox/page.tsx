import Link from "next/link";
import { InboxList } from "@/app/components/inbox/InboxList";
import { ThreadPane } from "@/app/components/inbox/ThreadPane";
import { Empty, PageHeader } from "@/app/components/ui";
import { StudioError, api } from "@/lib/studio";
import type { InboxDetail } from "@/lib/types.inbox";

export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const FILTER_KEYS = ["view", "q", "assigned", "status", "sentiment", "type", "account", "platform", "date_from", "date_to", "offset"];

export default async function Inbox({ params, searchParams }: { params: Promise<{ workspaceId: string }>; searchParams: Promise<Search> }) {
  const { workspaceId } = await params;
  const q = await searchParams;
  const query = new URLSearchParams();
  for (const k of FILTER_KEYS) {
    const v = q[k];
    if (v === undefined) continue;
    for (const x of Array.isArray(v) ? v : [v]) if (x) query.append(k, x);
  }
  const selected = typeof q.m === "string" ? q.m : null;

  const [feed, detail] = await Promise.all([
    api.inbox(workspaceId, query),
    selected
      ? api.inboxMessage(workspaceId, selected).catch((e) => {
          if (e instanceof StudioError && e.status === 404) return null;
          throw e;
        })
      : Promise.resolve(null as InboxDetail | null),
  ]);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <PageHeader title="Social Inbox">
        <div className="flex items-center gap-3 text-sm" style={{ color: "var(--muted)" }}>
          <span>{feed.unread_count} unread</span>
          {feed.can_manage && (
            <Link href={`/w/${workspaceId}/inbox/settings`} className="hover:text-black">
              Saved replies &amp; SLA
            </Link>
          )}
        </div>
      </PageHeader>
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[22rem_1fr]">
        <InboxList workspaceId={workspaceId} feed={feed} selectedId={selected} query={Object.fromEntries(query.entries())} />
        <div className="panel min-h-0 overflow-y-auto p-5">
          {detail ? <ThreadPane workspaceId={workspaceId} message={detail} team={feed.team} canReply={feed.can_reply} /> : <Empty>Select a message to read the thread.</Empty>}
        </div>
      </div>
    </div>
  );
}
