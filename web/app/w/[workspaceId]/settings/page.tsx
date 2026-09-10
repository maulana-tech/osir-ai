import { WorkspaceSettingsView } from "@/app/components/settings/WorkspaceSettingsView";
import { PageHeader } from "@/app/components/ui";
import { StudioError, studio } from "@/lib/studio";
import type { Clients, WorkspaceSettings } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function SettingsPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const settings = await studio<WorkspaceSettings>(`/api/web/workspaces/${workspaceId}/settings`);
  let clients: Clients | null = null;
  if (settings.is_owner_or_manager) {
    try {
      clients = await studio<Clients>(`/api/web/workspaces/${workspaceId}/clients`);
    } catch (e) {
      if (!(e instanceof StudioError && e.status === 403)) throw e;
    }
  }
  return (
    <div>
      <PageHeader title="Workspace settings" />
      <WorkspaceSettingsView workspaceId={workspaceId} settings={settings} clients={clients} />
    </div>
  );
}
