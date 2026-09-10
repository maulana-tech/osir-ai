"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { addDays, addMonths, dayLabel, monthGrid, pad, periodLabel, toLocal, weekStart } from "@/lib/calendar";
import { call } from "@/lib/client";
import type { CalendarData, Chip, OpenSlot } from "@/lib/types.calendar";

type View = "month" | "week" | "day";

const PLATFORM_SHORT: Record<string, string> = {
  facebook: "FB",
  instagram: "IG",
  instagram_login: "IG",
  linkedin_personal: "in",
  linkedin_company: "in",
  tiktok: "TT",
  youtube: "YT",
  pinterest: "P",
  threads: "@",
  bluesky: "BS",
  google_business: "G",
  mastodon: "M",
  devto: "DEV",
};

const STATUS_STYLE: Record<string, React.CSSProperties> = {
  scheduled: { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" },
  published: { background: "#e5e5e5", color: "#0a0a0a", borderColor: "#e5e5e5" },
  draft: { background: "#fff", color: "#0a0a0a", borderColor: "#a3a3a3", borderStyle: "dashed" },
  failed: { background: "#fef2f2", color: "#dc2626", borderColor: "#dc2626" },
};

const TIMEZONES = ["UTC", "Asia/Jakarta", "Asia/Singapore", "Asia/Tokyo", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Australia/Sydney"];

interface Props {
  workspaceId: string;
  view: View;
  date: string;
  data: CalendarData;
  channels: string[];
  statuses: string[];
}

function href(workspaceId: string, q: Record<string, string | string[] | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, v);
  }
  return `/w/${workspaceId}/calendar?${p}`;
}

export function CalendarBoard({ workspaceId, view, date, data, channels, statuses }: Props) {
  const router = useRouter();
  const tz = data.display_timezone;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const base = { view, date, tz: tz === data.workspace_timezone ? undefined : tz, channel: channels, status: statuses };

  const step = (n: number) => (view === "month" ? addMonths(date, n) : addDays(date, view === "week" ? 7 * n : n));
  const composeUrl = (slot?: OpenSlot) =>
    slot
      ? `/w/${workspaceId}/compose?scheduled_date=${slot.compose_date}&scheduled_time=${slot.compose_time}&account=${slot.account.id}`
      : `/w/${workspaceId}/compose`;

  // Index chips and slots by display-tz day (and hour for week/day views).
  const byDay = new Map<string, Chip[]>();
  const byHour = new Map<string, Chip[]>();
  for (const c of data.chips) {
    if (!c.at) continue;
    const l = toLocal(c.at, tz);
    byDay.set(l.date, [...(byDay.get(l.date) ?? []), c]);
    const k = `${l.date}|${l.hour}`;
    byHour.set(k, [...(byHour.get(k) ?? []), c]);
  }
  const slotsByDay = new Map<string, OpenSlot[]>();
  const slotsByHour = new Map<string, OpenSlot[]>();
  for (const s of data.open_slots) {
    const l = toLocal(s.at, tz);
    slotsByDay.set(l.date, [...(slotsByDay.get(l.date) ?? []), s]);
    const k = `${l.date}|${l.hour}`;
    slotsByHour.set(k, [...(slotsByHour.get(k) ?? []), s]);
  }

  async function drop(chipId: string, newLocal: string) {
    setError(null);
    setBusy(chipId);
    try {
      await call(`/api/web/workspaces/${workspaceId}/calendar/reschedule`, {
        method: "POST",
        body: JSON.stringify({ platform_post_id: chipId, new_local: newLocal, tz }),
      });
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not move the post");
    } finally {
      setBusy(null);
    }
  }

  function onDrop(e: React.DragEvent, dayDate: string, hour?: number) {
    e.preventDefault();
    const chipId = e.dataTransfer.getData("text/chip");
    const chip = data.chips.find((c) => c.id === chipId);
    if (!chip || !chip.at) return;
    const l = toLocal(chip.at, tz);
    const h = hour ?? l.hour;
    const m = hour === undefined ? l.minute : l.minute;
    void drop(chipId, `${dayDate}T${pad(h)}:${pad(m)}`);
  }

  const ChipView = ({ c, compact }: { c: Chip; compact?: boolean }) => {
    const l = c.at ? toLocal(c.at, tz) : null;
    return (
      <a
        href={`/w/${workspaceId}/compose/${c.post_id}`}
        draggable={c.is_reschedulable}
        onDragStart={(e) => e.dataTransfer.setData("text/chip", c.id)}
        title={`${c.account.name} · ${c.status}${c.publish_error ? `\n${c.publish_error}` : ""}`}
        className="block truncate rounded border px-1.5 py-0.5 text-[11px] leading-4"
        style={{ ...(STATUS_STYLE[c.status] ?? { background: "#f5f5f5", color: "#0a0a0a", borderColor: "#e5e5e5" }), opacity: busy === c.id ? 0.4 : 1, cursor: c.is_reschedulable ? "grab" : "pointer" }}
      >
        <span className="font-bold">{PLATFORM_SHORT[c.platform] ?? c.platform.slice(0, 2)}</span>{" "}
        {l && <span>{`${pad(l.hour)}:${pad(l.minute)}`}</span>}
        {!compact && <span> · {c.title || c.caption || "(no caption)"}</span>}
      </a>
    );
  };

  const SlotView = ({ s }: { s: OpenSlot }) => {
    const l = toLocal(s.at, tz);
    return s.is_past ? (
      <span className="block truncate px-1.5 text-[11px]" style={{ color: "#a3a3a3" }}>
        {`${pad(l.hour)}:${pad(l.minute)}`} {s.account.name}
      </span>
    ) : (
      <a href={composeUrl(s)} className="block truncate rounded border border-dashed px-1.5 text-[11px] hover:border-black" style={{ borderColor: "#d4d4d4", color: "#737373" }} title={`Open slot for ${s.account.name}`}>
        + {`${pad(l.hour)}:${pad(l.minute)}`} {s.account.name}
      </a>
    );
  };

  const toolbar = (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-1">
        <Link className="btn" href={href(workspaceId, { ...base, date: step(-1) })}>
          ‹
        </Link>
        <Link className="btn" href={href(workspaceId, { ...base, date: data.today })}>
          Today
        </Link>
        <Link className="btn" href={href(workspaceId, { ...base, date: step(1) })}>
          ›
        </Link>
      </div>
      <h2 className="text-base font-semibold">{periodLabel(view, date)}</h2>
      <div className="ml-auto flex items-center gap-1 text-xs">
        {(["month", "week", "day"] as View[]).map((v) => (
          <Link key={v} className="btn" style={v === view ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined} href={href(workspaceId, { ...base, view: v })}>
            {v}
          </Link>
        ))}
        <Link className="btn" href={href(workspaceId, { ...base, view: "list" })}>
          list
        </Link>
      </div>
      <select
        className="input w-auto"
        value={tz}
        aria-label="Display timezone"
        onChange={(e) => router.push(href(workspaceId, { ...base, tz: e.target.value }))}
      >
        {[data.workspace_timezone, ...TIMEZONES.filter((t) => t !== data.workspace_timezone)].map((t) => (
          <option key={t} value={t}>
            {t === data.workspace_timezone ? `${t} (workspace)` : t}
          </option>
        ))}
      </select>
    </div>
  );

  const filters = (
    <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
      {data.filters.channels.map((c) => {
        const on = channels.includes(c.id);
        const next = on ? channels.filter((x) => x !== c.id) : [...channels, c.id];
        return (
          <Link key={c.id} href={href(workspaceId, { ...base, channel: next })} className="pill" style={on ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined} title={c.connected ? "" : "not connected"}>
            {PLATFORM_SHORT[c.platform] ?? c.platform} {c.name}
          </Link>
        );
      })}
      <select
        className="input w-auto"
        value={statuses[0] ?? ""}
        aria-label="Status"
        onChange={(e) => router.push(href(workspaceId, { ...base, status: e.target.value ? [e.target.value] : [] }))}
      >
        <option value="">all statuses</option>
        {data.filters.statuses.map((s) => (
          <option key={s} value={s}>
            {s.replace("_", " ")}
          </option>
        ))}
      </select>
    </div>
  );

  let body: React.ReactNode;
  if (view === "month") {
    const weeks = monthGrid(date);
    const month = date.slice(0, 7);
    body = (
      <div className="panel overflow-hidden">
        <div className="grid grid-cols-7 border-b text-[11px] font-semibold uppercase tracking-wide" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
            <div key={d} className="px-2 py-1.5">
              {d}
            </div>
          ))}
        </div>
        {weeks.map((week, i) => (
          <div key={i} className="grid grid-cols-7 border-b last:border-b-0" style={{ borderColor: "var(--line)" }}>
            {week.map((d) => {
              const chips = byDay.get(d) ?? [];
              const slots = slotsByDay.get(d) ?? [];
              const inMonth = d.startsWith(month);
              const isToday = d === data.today;
              return (
                <div
                  key={d}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => onDrop(e, d)}
                  className="min-h-28 space-y-0.5 border-r p-1 last:border-r-0"
                  style={{ borderColor: "var(--line)", background: inMonth ? "#fff" : "#fafafa", opacity: inMonth ? 1 : 0.6 }}
                >
                  <div className="mb-1 flex items-center justify-between px-1 text-[11px]">
                    <span className={isToday ? "rounded-full px-1.5 font-bold" : ""} style={isToday ? { background: "#0a0a0a", color: "#fff" } : { color: "var(--muted)" }}>
                      {Number(d.slice(8, 10))}
                    </span>
                    {d >= data.today && (
                      <a href={composeUrl()} className="hover:text-black" style={{ color: "#a3a3a3" }} title="New post">
                        +
                      </a>
                    )}
                  </div>
                  {chips.slice(0, 4).map((c) => (
                    <ChipView key={c.id} c={c} compact />
                  ))}
                  {chips.length > 4 && (
                    <Link href={href(workspaceId, { ...base, view: "day", date: d })} className="block px-1 text-[11px]" style={{ color: "var(--muted)" }}>
                      +{chips.length - 4} more
                    </Link>
                  )}
                  {slots.slice(0, 2).map((s, j) => (
                    <SlotView key={j} s={s} />
                  ))}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  } else {
    const days = view === "week" ? Array.from({ length: 7 }, (_, i) => addDays(weekStart(date), i)) : [date];
    const nowLocal = toLocal(new Date().toISOString(), tz);
    body = (
      <div className="panel overflow-x-auto">
        <div className="grid" style={{ gridTemplateColumns: `4rem repeat(${days.length}, minmax(0, 1fr))` }}>
          <div className="border-b" style={{ borderColor: "var(--line)" }} />
          {days.map((d) => (
            <div key={d} className="border-b border-l px-2 py-1.5 text-xs font-semibold" style={{ borderColor: "var(--line)", color: d === data.today ? "#0a0a0a" : "var(--muted)" }}>
              {dayLabel(d)}
            </div>
          ))}
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="contents">
              <div className="border-b px-2 py-1 text-[11px]" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
                {pad(h)}:00
              </div>
              {days.map((d) => {
                const k = `${d}|${h}`;
                const chips = byHour.get(k) ?? [];
                const slots = slotsByHour.get(k) ?? [];
                const isNow = d === nowLocal.date && h === nowLocal.hour;
                return (
                  <div
                    key={k}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => onDrop(e, d, h)}
                    className="min-h-10 space-y-0.5 border-b border-l p-0.5"
                    style={{ borderColor: "var(--line)", background: isNow ? "#f5f5f5" : undefined }}
                  >
                    {chips.map((c) => (
                      <ChipView key={c.id} c={c} />
                    ))}
                    {slots.map((s, j) => (
                      <SlotView key={j} s={s} />
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      {toolbar}
      {filters}
      {error && (
        <div className="mb-3 rounded-lg border px-3 py-2 text-sm" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          {error}
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_16rem]">
        {body}
        <aside className="space-y-4">
          <div className="panel p-4">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Unscheduled drafts
            </div>
            {data.unscheduled_drafts.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                None. Drag a chip to a day to schedule it.
              </p>
            ) : (
              <ul className="space-y-1">
                {data.unscheduled_drafts.map((d) => (
                  <li key={d.id}>
                    <a href={`/w/${workspaceId}/compose/${d.id}`} className="block truncate rounded px-1.5 py-1 text-xs hover:bg-neutral-100">
                      {d.title || d.caption || "(empty draft)"}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="panel p-4 text-[11px]" style={{ color: "var(--muted)" }}>
            <div className="mb-1 font-semibold uppercase tracking-wide">Legend</div>
            <div className="space-y-1">
              <div>
                <span className="inline-block rounded border px-1" style={STATUS_STYLE.scheduled}>scheduled</span> waits for the publisher
              </div>
              <div>
                <span className="inline-block rounded border px-1" style={STATUS_STYLE.draft}>draft</span> drop on a day to schedule
              </div>
              <div>
                <span className="inline-block rounded border px-1" style={STATUS_STYLE.published}>published</span> cannot move
              </div>
              <div>Dashed + rows are open posting slots.</div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
