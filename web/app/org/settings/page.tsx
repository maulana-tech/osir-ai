import { OrgSettingsView } from "@/app/components/org/OrgSettingsView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Org } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function OrgSettingsPage() {
  const org = await studio<Org>("/api/web/org/");
  return (
    <div>
      <PageHeader title="Organization" />
      <OrgSettingsView org={org} />
    </div>
  );
}
