import Link from "next/link";
import { NotificationsView } from "@/app/components/me/NotificationsView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Notifications } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function NotificationsPage({ searchParams }: { searchParams: Promise<{ event_type?: string; read_status?: string; page?: string }> }) {
  const q = await searchParams;
  const params = new URLSearchParams();
  if (q.event_type) params.set("event_type", q.event_type);
  if (q.read_status) params.set("read_status", q.read_status);
  if (q.page) params.set("page", q.page);
  const data = await studio<Notifications>(`/api/web/me/notifications?${params}`);
  return (
    <div>
      <PageHeader title="Notifications">
        <Link href="/me/notifications/preferences" className="btn">
          Preferences
        </Link>
      </PageHeader>
      <NotificationsView data={data} filters={{ event_type: q.event_type ?? "", read_status: q.read_status ?? "" }} />
    </div>
  );
}
