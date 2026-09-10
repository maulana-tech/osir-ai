"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { addDays, addMonths, dayLabel, monthGrid, pad, periodLabel, toLocal, weekStart } from "@/lib/calendar";
import type { OrgCalendar, OrgChip } from "@/lib/types.calendar";

type Filters = { workspace: string[]; channel: string; status: string; tag: string };

function href(q: { view: string; date: string } & Filters) {
  const p = new URLSearchParams({ view: q.view, date: q.date });
  q.workspace.forEach((w) => p.append("workspace", w));
  if (q.channel) p.set("channel", q.channel);
  if (q.status) p.set("status", q.status);
  if (q.tag) p.set("tag", q.tag);
  return `/org/calendar?${p}`;
}

export function OrgCalendarView({ data, view, date, filters }: { data: OrgCalendar; view: "month" | "week"; date: string; filters: Filters }) {
  const router = useRouter();
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const base = { view, date, ...filters };
  const step = (n: number) => (view === "month" ? addMonths(date, n) : addDays(date, 7 * n));
  const byDay = new Map<string, OrgChip[]>();
  for (const c of data.chips) {
    if (!c.at) continue;
    const l = toLocal(c.at, tz);
    byDay.set(l.date, [...(byDay.get(l.date) ?? []), c]);
  }
  const Chip = ({ c }: { c: OrgChip }) => {
    const l = c.at ? toLocal(c.at, tz) : null;
    return (
      <Link href={`/w/${c.workspace_id}/compose/${c.post_id}`} className="block truncate rounded px-1.5 py-0.5 text-[11px] leading-4" style={{ background: c.color, color: "#fff", opacity: c.status === "published" ? 0.6 : 1 }} title={`${c.workspace_name} · ${c.account.name} · ${c.status}`}>
        {l && `${pad(l.hour)}:${pad(l.minute)} `}
        {c.title || c.caption || c.account.name}
      </Link>
    );
  };
  const days = view === "week" ? Array.from({ length: 7 }, (_, i) => addDays(weekStart(date), i)) : [];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <Link className="btn" href={href({ ...base, date: step(-1) })}>
            ‹
          </Link>
          <Link className="btn" href={href({ ...base, date: data.today })}>
            Today
          </Link>
          <Link className="btn" href={href({ ...base, date: step(1) })}>
            ›
          </Link>
        </div>
        <h2 className="text-base font-semibold">{periodLabel(view, date)}</h2>
        <div className="ml-auto flex gap-1 text-xs">
          {(["month", "week"] as const).map((v) => (
            <Link key={v} className="btn" style={v === view ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined} href={href({ ...base, view: v })}>
              {v}
            </Link>
          ))}
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
        {data.workspaces.map((w) => {
          const on = filters.workspace.includes(w.id);
          const next = on ? filters.workspace.filter((x) => x !== w.id) : [...filters.workspace, w.id];
          return (
            <Link key={w.id} href={href({ ...base, workspace: next })} className="pill" style={{ borderColor: w.color, background: on ? w.color : undefined, color: on ? "#fff" : undefined }}>
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: on ? "#fff" : w.color }} />
              {w.name}
            </Link>
          );
        })}
        <select className="input w-auto" value={filters.channel} onChange={(e) => router.push(href({ ...base, channel: e.target.value }))}>
          <option value="">all channels</option>
          {data.accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.platform})
            </option>
          ))}
        </select>
        <select className="input w-auto" value={filters.status} onChange={(e) => router.push(href({ ...base, status: e.target.value }))}>
          <option value="">all statuses</option>
          {data.statuses.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        {data.tags.length > 0 && (
          <select className="input w-auto" value={filters.tag} onChange={(e) => router.push(href({ ...base, tag: e.target.value }))}>
            <option value="">all tags</option>
            {data.tags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        )}
        <span style={{ color: "var(--muted)" }}>Times in {tz}</span>
      </div>
      <div className="panel overflow-hidden">
        <div className="grid grid-cols-7 border-b text-[11px] font-semibold uppercase tracking-wide" style={{ borderColor: "var(--line)", color: "var(--muted)" }}>
          {(view === "week" ? days.map(dayLabel) : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]).map((d) => (
            <div key={d} className="px-2 py-1.5">
              {d}
            </div>
          ))}
        </div>
        {(view === "week" ? [days] : monthGrid(date)).map((week, i) => (
          <div key={i} className="grid grid-cols-7 border-b last:border-b-0" style={{ borderColor: "var(--line)" }}>
            {week.map((d) => {
              const chips = byDay.get(d) ?? [];
              const inMonth = view === "week" || d.startsWith(date.slice(0, 7));
              return (
                <div key={d} className="space-y-0.5 border-r p-1 last:border-r-0" style={{ borderColor: "var(--line)", minHeight: view === "week" ? 240 : 112, background: inMonth ? "#fff" : "#fafafa", opacity: inMonth ? 1 : 0.6 }}>
                  <div className="mb-1 px-1 text-[11px]" style={d === data.today ? { fontWeight: 700 } : { color: "var(--muted)" }}>
                    {Number(d.slice(8, 10))}
                  </div>
                  {chips.slice(0, view === "week" ? 20 : 5).map((c) => (
                    <Chip key={c.id} c={c} />
                  ))}
                  {view === "month" && chips.length > 5 && (
                    <Link href={href({ ...base, view: "week", date: d })} className="block px-1 text-[11px]" style={{ color: "var(--muted)" }}>
                      +{chips.length - 5} more
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
