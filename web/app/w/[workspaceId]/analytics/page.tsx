import { redirect } from "next/navigation";
import { Empty, PageHeader, Section } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { AnalyticsIndex } from "@/lib/types.analytics";

export const dynamic = "force-dynamic";

export default async function AnalyticsIndexPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const idx = await studio<AnalyticsIndex>(`/api/web/workspaces/${workspaceId}/analytics`);
  if (idx.preferred_account_id) redirect(`/w/${workspaceId}/analytics/${idx.preferred_account_id}`);
  return (
    <div>
      <PageHeader title="Analytics" />
      <Section title="No channels">
        <Empty>
          {idx.enabled ? (
            <>
              Connect a channel first.{" "}
              <a href={`/social-accounts/${workspaceId}/connect/`} className="underline">
                Connect
              </a>
            </>
          ) : (
            "Analytics is switched off for this deployment."
          )}
        </Empty>
      </Section>
    </div>
  );
}
