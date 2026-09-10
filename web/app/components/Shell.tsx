import { notFound, redirect } from "next/navigation";
import { AutoRefresh } from "@/app/components/AutoRefresh";
import { Checklist } from "@/app/components/Checklist";
import { RememberWorkspace } from "@/app/components/RememberWorkspace";
import { Sidebar } from "@/app/components/Sidebar";
import { StudioError, api, studio } from "@/lib/studio";
import type { Checklist as ChecklistData } from "@/lib/types.admin";

/**
 * The signed-in app frame: sidebar for a workspace plus the page body.
 * Workspace pages pass their id; organization and account pages fall back to
 * the workspace the person was last in.
 */
export async function Shell({ workspaceId, children }: { workspaceId?: string; children: React.ReactNode }) {
  const me = await api.me(workspaceId);
  if (!me.user.tos_accepted) redirect("/accounts/accept-terms/");
  const wsId = workspaceId ?? me.current_workspace_id ?? me.workspaces[0]?.id;
  if (!wsId) redirect("/org/workspaces");
  const workspace = me.workspaces.find((w) => w.id === wsId);
  if (!workspace) notFound();

  let sidebar;
  let checklist: ChecklistData | null = null;
  try {
    [sidebar, checklist] = await Promise.all([
      api.sidebar(wsId),
      workspaceId ? studio<ChecklistData>(`/api/web/workspaces/${wsId}/checklist`) : Promise.resolve(null),
    ]);
  } catch (e) {
    if (e instanceof StudioError && (e.status === 403 || e.status === 404)) notFound();
    throw e;
  }

  return (
    <div className="flex min-h-screen">
      <AutoRefresh seconds={30} />
      {workspaceId && <RememberWorkspace workspaceId={workspaceId} current={me.current_workspace_id} />}
      <Sidebar me={me} workspace={workspace} sidebar={sidebar} />
      <main className="min-w-0 flex-1 px-8 py-8">
        {checklist && !checklist.dismissed && <Checklist workspaceId={wsId} data={checklist} />}
        {children}
      </main>
    </div>
  );
}
