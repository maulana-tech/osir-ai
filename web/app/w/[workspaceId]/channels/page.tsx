import { ChannelsView } from "@/app/components/channels/ChannelsView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Channels } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function ChannelsPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const data = await studio<Channels>(`/api/web/workspaces/${workspaceId}/channels`);
  return (
    <div>
      <PageHeader title="Channels" />
      <ChannelsView workspaceId={workspaceId} data={data} />
    </div>
  );
}
