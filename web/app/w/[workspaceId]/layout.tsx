import { notFound, redirect } from "next/navigation";
import { AutoRefresh } from "@/app/components/AutoRefresh";
import { RememberWorkspace } from "@/app/components/RememberWorkspace";
import { Sidebar } from "@/app/components/Sidebar";
import { StudioError, api } from "@/lib/studio";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const me = await api.me(workspaceId);
  if (!me.user.tos_accepted) redirect("/accounts/accept-terms/");
  const workspace = me.workspaces.find((w) => w.id === workspaceId);
  if (!workspace) notFound();

  let sidebar;
  try {
    sidebar = await api.sidebar(workspaceId);
  } catch (e) {
    if (e instanceof StudioError && (e.status === 403 || e.status === 404)) notFound();
    throw e;
  }

  return (
    <div className="flex min-h-screen">
      <AutoRefresh seconds={30} />
      <RememberWorkspace workspaceId={workspaceId} current={me.current_workspace_id} />
      <Sidebar me={me} workspace={workspace} sidebar={sidebar} />
      <main className="min-w-0 flex-1 px-8 py-8">{children}</main>
    </div>
  );
}
