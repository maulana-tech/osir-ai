import { Shell } from "@/app/components/Shell";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({ children, params }: { children: React.ReactNode; params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  return <Shell workspaceId={workspaceId}>{children}</Shell>;
}
