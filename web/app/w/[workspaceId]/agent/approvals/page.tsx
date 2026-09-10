import { redirect } from "next/navigation";

/** The approval queue is a first-class page now; keep the old console URL working. */
export default async function LegacyApprovals({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  redirect(`/w/${workspaceId}/approvals`);
}
