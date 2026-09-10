import Link from "next/link";
import { FeedsTab } from "@/app/components/create/FeedsTab";
import { IdeasBoard } from "@/app/components/create/IdeasBoard";
import { TemplatesGallery } from "@/app/components/create/TemplatesGallery";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Board, FeedsData, Templates } from "@/lib/types.composer";

export const dynamic = "force-dynamic";

const TABS = [
  { key: "ideas", label: "Ideas" },
  { key: "templates", label: "Templates" },
  { key: "feeds", label: "Feeds" },
];

export default async function CreatePage({ params, searchParams }: { params: Promise<{ workspaceId: string }>; searchParams: Promise<{ tab?: string; tag?: string; feed_id?: string }> }) {
  const { workspaceId } = await params;
  const q = await searchParams;
  const tab = TABS.some((t) => t.key === q.tab) ? q.tab! : "ideas";
  const base = `/api/web/workspaces/${workspaceId}/composer`;
  const unsplash = false;
  let body: React.ReactNode;
  if (tab === "ideas") {
    const board = await studio<Board>(`${base}/ideas${q.tag ? `?tag=${encodeURIComponent(q.tag)}` : ""}`);
    body = <IdeasBoard workspaceId={workspaceId} board={board} unsplash={unsplash} />;
  } else if (tab === "templates") {
    body = <TemplatesGallery workspaceId={workspaceId} data={await studio<Templates>(`${base}/templates`)} />;
  } else {
    body = <FeedsTab workspaceId={workspaceId} data={await studio<FeedsData>(`${base}/feeds?feed_id=${q.feed_id ?? "all"}`)} />;
  }
  return (
    <div>
      <PageHeader title="Create">
        <div className="flex items-center gap-2">
          <Link href={`/w/${workspaceId}/import`} className="btn">
            Import CSV
          </Link>
          <Link href={`/w/${workspaceId}/compose`} className="btn btn-accent">
            New post
          </Link>
        </div>
      </PageHeader>
      <div className="mb-4 flex gap-1 text-xs">
        {TABS.map((t) => (
          <Link key={t.key} className="btn" style={t.key === tab ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined} href={`/w/${workspaceId}/create?tab=${t.key}`}>
            {t.label}
          </Link>
        ))}
      </div>
      {body}
    </div>
  );
}
