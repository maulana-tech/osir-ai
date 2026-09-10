import { ApprovalsView } from "@/app/components/approvals/ApprovalsView";
import { PageHeader } from "@/app/components/ui";
import { api } from "@/lib/studio";

export const dynamic = "force-dynamic";

export default async function Approvals({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const [posts, me] = await Promise.all([api.approvals(workspaceId), api.me(workspaceId)]);
  return (
    <div>
      <PageHeader title="Approvals" />
      <ApprovalsView posts={posts} workspaceId={workspaceId} userId={me.user.id} />
    </div>
  );
}
