import Link from "next/link";
import { QueuesView } from "@/app/components/calendar/QueuesView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { QueuesData } from "@/lib/types.calendar";

export const dynamic = "force-dynamic";

export default async function QueuesPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const data = await studio<QueuesData>(`/api/web/workspaces/${workspaceId}/calendar/queues`);
  return (
    <div>
      <PageHeader title="Queues">
        <Link href={`/w/${workspaceId}/calendar`} className="btn">
          Back to calendar
        </Link>
      </PageHeader>
      <QueuesView workspaceId={workspaceId} data={data} />
    </div>
  );
}
