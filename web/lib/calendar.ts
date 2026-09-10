/** Date helpers for the calendar UI. All "local" values are in the display timezone. */

export interface LocalParts {
  date: string; // YYYY-MM-DD
  hour: number;
  minute: number;
}

const fmtCache = new Map<string, Intl.DateTimeFormat>();

function formatter(tz: string): Intl.DateTimeFormat {
  let f = fmtCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    fmtCache.set(tz, f);
  }
  return f;
}

/** Split an ISO instant into wall-clock parts in `tz`. */
export function toLocal(iso: string, tz: string): LocalParts {
  const parts = Object.fromEntries(
    formatter(tz)
      .formatToParts(new Date(iso))
      .filter((p) => p.type !== "literal")
      .map((p) => [p.type, p.value]),
  ) as Record<string, string>;
  const hour = Number(parts.hour) % 24; // "24" at midnight in some engines
  return { date: `${parts.year}-${parts.month}-${parts.day}`, hour, minute: Number(parts.minute) };
}

export function addDays(date: string, n: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Monday of the week containing `date`. */
export function weekStart(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  const dow = (d.getUTCDay() + 6) % 7; // Monday = 0
  return addDays(date, -dow);
}

export function monthStart(date: string): string {
  return `${date.slice(0, 7)}-01`;
}

export function addMonths(date: string, n: number): string {
  const [y, m] = date.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return d.toISOString().slice(0, 10);
}

/** Six-week grid (Monday first) covering the month of `date`. */
export function monthGrid(date: string): string[][] {
  const first = monthStart(date);
  const start = weekStart(first);
  const weeks: string[][] = [];
  for (let w = 0; w < 6; w++) {
    weeks.push(Array.from({ length: 7 }, (_, i) => addDays(start, w * 7 + i)));
  }
  return weeks;
}

/** The window the API should return for a view anchored on `date`. */
export function windowFor(view: string, date: string): { start: string; end: string } {
  if (view === "day") return { start: date, end: date };
  if (view === "week") {
    const s = weekStart(date);
    return { start: s, end: addDays(s, 6) };
  }
  const grid = monthGrid(date);
  return { start: grid[0][0], end: grid[5][6] };
}

export function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

export function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}

export function periodLabel(view: string, date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (view === "day") return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
  if (view === "week") {
    const { start, end } = windowFor("week", date);
    return `${dayLabel(start)} – ${dayLabel(end)}`;
  }
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
}
