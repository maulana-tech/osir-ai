import { AccountView } from "@/app/components/me/AccountView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Profile } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const profile = await studio<Profile>("/api/web/me/account");
  return (
    <div>
      <PageHeader title="Account" />
      <AccountView profile={profile} />
    </div>
  );
}
