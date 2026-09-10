"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Empty, Section, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { NotificationRow, Notifications } from "@/lib/types.admin";

/** Where a notification points, if its payload names something we render. */
function target(n: NotificationRow): string | null {
  const ws = n.data.workspace_id;
  if (!ws) return null;
  if (n.data.post_id) return `/w/${ws}/approvals`;
  if (n.data.message_id) return `/w/${ws}/inbox/${n.data.message_id}`;
  if (n.event_type.startsWith("agent_")) return `/w/${ws}/agent`;
  return `/w/${ws}/calendar`;
}

export function NotificationsView({ data, filters }: { data: Notifications; filters: { event_type: string; read_status: string } }) {
  const router = useRouter();
  const { run, busy, Feedback } = useAction();
  const setFilter = (k: string, v: string) => {
    const p = new URLSearchParams();
    const next = { ...filters, [k]: v };
    if (next.event_type) p.set("event_type", next.event_type);
    if (next.read_status) p.set("read_status", next.read_status);
    router.push(`/me/notifications?${p}`);
  };
  const pageLink = (page: number) => {
    const p = new URLSearchParams();
    if (filters.event_type) p.set("event_type", filters.event_type);
    if (filters.read_status) p.set("read_status", filters.read_status);
    p.set("page", String(page));
    return `/me/notifications?${p}`;
  };

  return (
    <Section title="History" hint={`${data.unread_count} unread`}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <select className="input w-auto" value={filters.event_type} onChange={(e) => setFilter("event_type", e.target.value)}>
          <option value="">All types</option>
          {data.event_types.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <select className="input w-auto" value={filters.read_status} onChange={(e) => setFilter("read_status", e.target.value)}>
          <option value="">Read and unread</option>
          <option value="unread">Unread</option>
          <option value="read">Read</option>
        </select>
        {data.unread_count > 0 && (
          <button className="btn ml-auto" disabled={busy} onClick={() => run(() => call("/api/web/me/notifications/read-all", { method: "POST" }), "All read")}>
            Mark all read
          </button>
        )}
      </div>
      {data.notifications.length === 0 ? (
        <Empty>Nothing here.</Empty>
      ) : (
        <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
          {data.notifications.map((n) => {
            const href = target(n);
            return (
              <li key={n.id} className="flex items-start gap-3 py-3 text-sm">
                <span className="mt-2 h-2 w-2 shrink-0 rounded-full" style={{ background: n.is_read ? "transparent" : "#0a0a0a" }} />
                <div className="min-w-0 flex-1">
                  <div className={n.is_read ? "" : "font-semibold"}>{href ? <Link href={href} className="hover:underline">{n.title}</Link> : n.title}</div>
                  {n.body && (
                    <div className="whitespace-pre-wrap text-xs" style={{ color: "var(--muted)" }}>
                      {n.body}
                    </div>
                  )}
                  <div className="text-xs" style={{ color: "var(--muted)" }}>
                    {timeAgo(n.created_at)}
                  </div>
                </div>
                {!n.is_read && (
                  <button className="btn" disabled={busy} onClick={() => run(() => call(`/api/web/me/notifications/${n.id}/read`, { method: "POST" }))}>
                    Mark read
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-3 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
        <span>
          Page {data.page} · {data.total} total
        </span>
        <span className="flex gap-3">
          {data.page > 1 && (
            <Link href={pageLink(data.page - 1)} className="underline">
              Newer
            </Link>
          )}
          {data.has_next && (
            <Link href={pageLink(data.page + 1)} className="underline">
              Older
            </Link>
          )}
        </span>
      </div>
      <Feedback />
    </Section>
  );
}
