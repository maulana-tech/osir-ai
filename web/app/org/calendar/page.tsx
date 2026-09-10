import { OrgCalendarView } from "@/app/components/calendar/OrgCalendarView";
import { PageHeader } from "@/app/components/ui";
import { windowFor } from "@/lib/calendar";
import { studio } from "@/lib/studio";
import type { OrgCalendar } from "@/lib/types.calendar";

export const dynamic = "force-dynamic";

export default async function OrgCalendarPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const q = await searchParams;
  const view = q.view === "week" ? "week" : "month";
  const today = new Date().toISOString().slice(0, 10);
  const date = typeof q.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : today;
  const { start, end } = windowFor(view, date);
  const p = new URLSearchParams({ start, end });
  const ws = q.workspace === undefined ? [] : Array.isArray(q.workspace) ? q.workspace : [q.workspace];
  for (const w of ws) p.append("workspace", w);
  for (const k of ["channel", "status", "tag"]) if (typeof q[k] === "string" && q[k]) p.set(k, q[k] as string);
  const data = await studio<OrgCalendar>(`/api/web/org/calendar?${p}`);
  return (
    <div>
      <PageHeader title="All workspaces" />
      <OrgCalendarView data={data} view={view} date={date} filters={{ workspace: ws, channel: (q.channel as string) ?? "", status: (q.status as string) ?? "", tag: (q.tag as string) ?? "" }} />
    </div>
  );
}
