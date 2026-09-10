import Link from "next/link";
import type { AgentRun, RunStatus } from "@/lib/types";

export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const STATUS_CLASS: Record<RunStatus, string> = {
  pending: "pill",
  running: "pill pill-accent",
  succeeded: "pill pill-ok",
  failed: "pill pill-bad",
};

export function StatusPill({ status }: { status: RunStatus }) {
  return <span className={STATUS_CLASS[status]}>{status}</span>;
}

export function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="panel p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
          {title}
        </h2>
        {hint && (
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            {hint}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

export function RunRow({ run, base }: { run: AgentRun; base: string }) {
  const actions = run.report?.actions?.length ?? 0;
  const decisions = run.report?.decisions_for_humans?.length ?? 0;
  return (
    <Link href={`${base}/runs/${run.id}`} className="flex items-center justify-between gap-4 rounded-lg px-3 py-2 hover:bg-neutral-50">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold capitalize">{run.task}</span>
          {run.dry_run && <span className="pill">dry run</span>}
          <StatusPill status={run.status} />
        </div>
        <div className="truncate text-xs" style={{ color: "var(--muted)" }}>
          {run.instruction || run.report?.notes || run.error || "scheduled run"}
        </div>
      </div>
      <div className="shrink-0 text-right text-xs" style={{ color: "var(--muted)" }}>
        <div>{timeAgo(run.created_at)}</div>
        {run.status === "succeeded" && (
          <div>
            {actions} actions · {decisions} for you
          </div>
        )}
      </div>
    </Link>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="py-6 text-center text-sm" style={{ color: "var(--muted)" }}>
      {children}
    </p>
  );
}

export function PageHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-baseline justify-between">
      <h1 className="text-xl font-bold">{title}</h1>
      {children}
    </div>
  );
}
