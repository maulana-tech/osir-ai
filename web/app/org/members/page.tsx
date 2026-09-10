import { MembersView } from "@/app/components/org/MembersView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Members } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function MembersPage() {
  const data = await studio<Members>("/api/web/org/members");
  return (
    <div>
      <PageHeader title="Team" />
      <MembersView data={data} />
    </div>
  );
}
