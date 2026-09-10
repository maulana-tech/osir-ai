import { WorkspacesView } from "@/app/components/org/WorkspacesView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { OrgWorkspaces } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function OrgWorkspacesPage() {
  const data = await studio<OrgWorkspaces>("/api/web/org/workspaces");
  return (
    <div>
      <PageHeader title="Workspaces" />
      <WorkspacesView data={data} />
    </div>
  );
}
