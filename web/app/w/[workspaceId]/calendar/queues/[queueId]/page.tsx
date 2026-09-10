import Link from "next/link";
import { QueueDetailView } from "@/app/components/calendar/QueueDetailView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { QueueDetail } from "@/lib/types.calendar";

export const dynamic = "force-dynamic";

export default async function QueueDetailPage({ params }: { params: Promise<{ workspaceId: string; queueId: string }> }) {
  const { workspaceId, queueId } = await params;
  const data = await studio<QueueDetail>(`/api/web/workspaces/${workspaceId}/calendar/queues/${queueId}`);
  return (
    <div>
      <PageHeader title={data.queue.name}>
        <Link href={`/w/${workspaceId}/calendar/queues`} className="btn">
          All queues
        </Link>
      </PageHeader>
      <QueueDetailView workspaceId={workspaceId} data={data} />
    </div>
  );
}
