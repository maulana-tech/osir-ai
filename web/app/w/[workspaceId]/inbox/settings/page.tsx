import { InboxSettings } from "@/app/components/inbox/InboxSettings";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Sla } from "@/lib/types.inbox";

export const dynamic = "force-dynamic";

export default async function InboxSettingsPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const [saved, sla] = await Promise.all([
    studio<{ saved_replies: { id: string; title: string; body: string }[] }>(`/api/web/workspaces/${workspaceId}/inbox/saved-replies`),
    studio<Sla>(`/api/web/workspaces/${workspaceId}/inbox/sla`),
  ]);
  return (
    <div>
      <PageHeader title="Inbox settings" />
      <InboxSettings workspaceId={workspaceId} savedReplies={saved.saved_replies} sla={sla} />
    </div>
  );
}
