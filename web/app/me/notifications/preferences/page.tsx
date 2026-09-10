import { PreferencesView } from "@/app/components/me/PreferencesView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Preferences } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function PreferencesPage() {
  const data = await studio<Preferences>("/api/web/me/notification-preferences");
  return (
    <div>
      <PageHeader title="Notification preferences" />
      <PreferencesView data={data} />
    </div>
  );
}
