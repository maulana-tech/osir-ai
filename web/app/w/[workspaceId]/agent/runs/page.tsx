import { Empty, PageHeader, RunRow, Section } from "@/app/components/ui";
import { api } from "@/lib/studio";

export const dynamic = "force-dynamic";

export default async function Runs({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const runs = await api.runs(workspaceId, 100);
  return (
    <div>
      <PageHeader title="Agent runs" />
      <Section title="Newest first">
        {runs.length === 0 ? (
          <Empty>No runs yet. Start the worker or a scheduled loop.</Empty>
        ) : (
          <div className="-mx-3">
            {runs.map((r) => (
              <RunRow key={r.id} run={r} base={`/w/${workspaceId}/agent`} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
