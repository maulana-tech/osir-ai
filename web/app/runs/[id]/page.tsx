import { notFound } from "next/navigation";
import { StudioError, studio } from "@/lib/studio";
import { Section, StatusPill, timeAgo } from "../../components/ui";

export const dynamic = "force-dynamic";

export default async function RunDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let run;
  try {
    run = await studio.run(id);
  } catch (e) {
    if (e instanceof StudioError && e.status === 404) notFound();
    throw e;
  }
  const report = run.report ?? {};
  return (
    <div className="space-y-6">
      <Section title={`${run.task} run`} hint={timeAgo(run.created_at)}>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <StatusPill status={run.status} />
          {run.dry_run && <span className="pill">dry run</span>}
          {run.triggered_by && (
            <span style={{ color: "var(--muted)" }}>asked by {run.triggered_by}</span>
          )}
        </div>
        {run.instruction && <p className="mt-3 whitespace-pre-wrap text-sm">“{run.instruction}”</p>}
        {run.error && (
          <pre className="mt-3 overflow-x-auto rounded-lg p-3 text-xs" style={{ color: "var(--bad)", background: "#160f0f" }}>
            {run.error}
          </pre>
        )}
      </Section>

      <Section title="Actions" hint={`${report.actions?.length ?? 0}`}>
        {report.actions?.length ? (
          <ul className="space-y-2 text-sm">
            {report.actions.map((a, i) => (
              <li key={i} className="flex gap-3">
                <span className="pill shrink-0">{a.kind}</span>
                <span>{a.summary}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            No actions taken.
          </p>
        )}
      </Section>

      <Section title="Handed to a human" hint={`${report.decisions_for_humans?.length ?? 0}`}>
        {report.decisions_for_humans?.length ? (
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {report.decisions_for_humans.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Nothing needed a person.
          </p>
        )}
      </Section>

      {report.notes && (
        <Section title="Notes">
          <p className="whitespace-pre-wrap text-sm">{report.notes}</p>
        </Section>
      )}
    </div>
  );
}
