import Link from "next/link";
import { SlotsView } from "@/app/components/calendar/SlotsView";
import { PageHeader } from "@/app/components/ui";
import { api, studio } from "@/lib/studio";
import type { SlotsData } from "@/lib/types.calendar";

export const dynamic = "force-dynamic";

export default async function SlotsPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const [data, me] = await Promise.all([studio<SlotsData>(`/api/web/workspaces/${workspaceId}/calendar/slots`), api.me(workspaceId)]);
  const canManage = !!me.workspaces.find((w) => w.id === workspaceId)?.permissions.includes("manage_social_accounts");
  return (
    <div>
      <PageHeader title="Posting slots">
        <Link href={`/w/${workspaceId}/calendar`} className="btn">
          Back to calendar
        </Link>
      </PageHeader>
      <SlotsView workspaceId={workspaceId} data={data} canManage={canManage} />
    </div>
  );
}
