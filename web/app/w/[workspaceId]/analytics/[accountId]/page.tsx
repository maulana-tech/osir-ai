import Link from "next/link";
import { notFound } from "next/navigation";
import { LineChart, Sparkline } from "@/app/components/analytics/Sparkline";
import { Empty, PageHeader, Section } from "@/app/components/ui";
import { StudioError, studio } from "@/lib/studio";
import type { AccountAnalytics, Derived, MetricCard } from "@/lib/types.analytics";

export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

function fmt(d: Derived): string {
  if (d.kind === "percent") return `${d.value.toFixed(2)}%`;
  if (d.kind === "minutes") return `${Math.round(d.value).toLocaleString()} min`;
  return Math.round(d.value).toLocaleString();
}

function Delta({ d }: { d: Derived }) {
  const sign = d.delta > 0 ? "+" : "";
  return (
    <span className="text-xs" style={{ color: d.delta < 0 ? "var(--bad)" : "var(--muted)" }}>
      {sign}
      {d.delta.toFixed(1)}% vs prior
    </span>
  );
}

function Card({ c }: { c: MetricCard }) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
        {c.label}
      </div>
      <div className="mt-1 flex items-end justify-between gap-2">
        <div>
          <div className="text-2xl font-bold">{fmt(c.derived)}</div>
          <Delta d={c.derived} />
        </div>
        <Sparkline series={c.derived.series} />
      </div>
    </div>
  );
}

export default async function AccountAnalyticsPage({ params, searchParams }: { params: Promise<{ workspaceId: string; accountId: string }>; searchParams: Promise<Search> }) {
  const { workspaceId, accountId } = await params;
  const q = await searchParams;
  const qs = new URLSearchParams();
  for (const k of ["range", "chart_metric", "table_range", "sort", "dir", "type", "page"]) {
    const v = q[k];
    if (typeof v === "string" && v) qs.set(k, v);
  }
  let data: AccountAnalytics;
  try {
    data = await studio<AccountAnalytics>(`/api/web/workspaces/${workspaceId}/analytics/accounts/${accountId}?${qs}`);
  } catch (e) {
    if (e instanceof StudioError && e.status === 404) notFound();
    throw e;
  }
  const base = `/w/${workspaceId}/analytics/${accountId}`;
  const href = (patch: Record<string, string | undefined>) => {
    const p = new URLSearchParams(qs);
    for (const [k, v] of Object.entries(patch)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    return `${base}?${p}`;
  };
  const a = data.account;
  const table = data.table;

  return (
    <div className="space-y-6">
      <PageHeader title="Analytics">
        <div className="flex items-center gap-2 text-xs">
          {data.range_choices.map((r) => (
            <Link key={r} href={href({ range: String(r), page: undefined })} className="btn" style={r === data.days ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined}>
              {r}d
            </Link>
          ))}
        </div>
      </PageHeader>

      <div className="flex flex-wrap gap-2 text-xs">
        {data.accounts.map((acc) => (
          <Link key={acc.id} href={`/w/${workspaceId}/analytics/${acc.id}${qs.get("range") ? `?range=${qs.get("range")}` : ""}`} className="pill" style={acc.id === a.id ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined} title={acc.unavailable_reason ?? ""}>
            {acc.platform_label}: {acc.name}
            {!acc.analytics_available && " (no analytics)"}
          </Link>
        ))}
      </div>

      {!a.analytics_available && (
        <div className="rounded-lg border px-4 py-3 text-sm" style={{ borderColor: "var(--line)", background: "#fafafa" }}>
          {a.unavailable_reason}
          {a.disabled_by_admin && " An organization admin can enable it under Settings."}
        </div>
      )}
      {a.needs_reconnect && a.analytics_available && (
        <div className="rounded-lg border px-4 py-3 text-sm" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          This channel was connected without analytics permissions.{" "}
          <a href={`/social-accounts/${workspaceId}/`} className="underline">
            Reconnect it
          </a>{" "}
          to start collecting data.
        </div>
      )}

      {data.is_fresh && a.analytics_available && (
        <Section title="Getting started">
          <Empty>Freshly connected. Metrics appear after the first published post and the first daily sync.</Empty>
        </Section>
      )}

      {data.hero_cards && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {data.follower_growth && <Card c={{ metric: "followers", label: "New followers", derived: data.follower_growth }} />}
          {data.hero_cards.map((c) => (
            <Card key={c.metric} c={c} />
          ))}
        </div>
      )}

      {data.chart && (
        <Section title={data.chart.label} hint={`last ${data.days} days`}>
          <div className="mb-3 flex flex-wrap gap-1 text-xs">
            {data.chart.chips.map((ch) => (
              <Link key={ch.key} href={href({ chart_metric: ch.key })} className="pill" style={ch.key === data.chart!.metric ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined}>
                {ch.label}
              </Link>
            ))}
          </div>
          <LineChart series={data.chart.derived.series} labels={data.chart.labels} />
        </Section>
      )}

      {data.engagement && (
        <Section title="Engagement">
          <div className="grid gap-4 md:grid-cols-[14rem_1fr]">
            <div>
              <div className="text-3xl font-bold">{fmt(data.engagement.rate)}</div>
              <Delta d={data.engagement.rate} />
              <div className="mt-2">
                <Sparkline series={data.engagement.rate.series} width={200} height={40} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {data.engagement.parts.map((p) => (
                <div key={p.metric} className="rounded-lg border p-3" style={{ borderColor: "var(--line)" }}>
                  <div className="text-[11px] uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                    {p.label}
                  </div>
                  <div className="text-lg font-semibold">{fmt(p.derived)}</div>
                  <Delta d={p.derived} />
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {table && (
        <Section title="Posts" hint={table.total ? `${table.page_from}–${table.page_to} of ${table.total}` : "none yet"}>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            {[["all", "all time"], ["7", "7d"], ["30", "30d"], ["90", "90d"]].map(([v, l]) => (
              <Link key={v} href={href({ table_range: v, page: undefined })} className="pill" style={(table.days_filter === null ? "all" : String(table.days_filter)) === v ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined}>
                {l}
              </Link>
            ))}
            {table.media_kinds.length > 1 && (
              <span className="ml-2 flex gap-1">
                <Link href={href({ type: undefined, page: undefined })} className="pill" style={table.type_filter === "all" ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined}>
                  any type
                </Link>
                {table.media_kinds.map((k) => (
                  <Link key={k} href={href({ type: k, page: undefined })} className="pill" style={table.type_filter === k ? { background: "#0a0a0a", color: "#fff", borderColor: "#0a0a0a" } : undefined}>
                    {k}
                  </Link>
                ))}
              </span>
            )}
          </div>
          {table.rows.length === 0 ? (
            <Empty>No published posts in this window.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                    <th className="py-2 pr-3">Post</th>
                    <th className="py-2 pr-3">
                      <Link href={href({ sort: "date", dir: table.sort_key === "date" ? table.toggled_dir : "desc" })}>Date{table.sort_key === "date" ? (table.sort_dir === "asc" ? " ↑" : " ↓") : ""}</Link>
                    </th>
                    {table.metric_labels.map((m) => (
                      <th key={m.key} className="py-2 pr-3 text-right">
                        <Link href={href({ sort: m.key, dir: table.sort_key === m.key ? table.toggled_dir : "desc" })}>
                          {m.label}
                          {table.sort_key === m.key ? (table.sort_dir === "asc" ? " ↑" : " ↓") : ""}
                        </Link>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: "var(--line)" }}>
                  {table.rows.map((r) => (
                    <tr key={r.platform_post_id}>
                      <td className="max-w-md py-2 pr-3">
                        <a href={`/workspace/${workspaceId}/analytics/posts/${r.post_id}/`} className="line-clamp-2 hover:underline">
                          {r.caption || "(no caption)"}
                        </a>
                        <span className="text-[11px]" style={{ color: "var(--muted)" }}>
                          {r.media_kind}
                        </span>
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3" style={{ color: "var(--muted)" }}>
                        {r.date}
                      </td>
                      {table.metric_labels.map((m) => (
                        <td key={m.key} className="whitespace-nowrap py-2 pr-3 text-right tabular-nums">
                          {m.kind === "percent" ? `${(r.stats[m.key] ?? 0).toFixed(2)}%` : Math.round(r.stats[m.key] ?? 0).toLocaleString()}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {table.total_pages > 1 && (
            <div className="mt-3 flex items-center justify-end gap-2 text-xs">
              {table.page > 1 && (
                <Link href={href({ page: String(table.page - 1) })} className="btn">
                  ‹ Newer
                </Link>
              )}
              <span style={{ color: "var(--muted)" }}>
                page {table.page} / {table.total_pages}
              </span>
              {table.page < table.total_pages && (
                <Link href={href({ page: String(table.page + 1) })} className="btn">
                  Older ›
                </Link>
              )}
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
