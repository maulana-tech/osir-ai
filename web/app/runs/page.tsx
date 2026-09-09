import { studio } from "@/lib/studio";
import { Empty, RunRow, Section } from "../components/ui";

export const dynamic = "force-dynamic";

export default async function Runs() {
  const runs = await studio.runs(100);
  return (
    <Section title="Agent runs" hint="newest first">
      {runs.length === 0 ? (
        <Empty>No runs yet. Start the worker or a scheduled loop.</Empty>
      ) : (
        <div className="-mx-3">
          {runs.map((r) => (
            <RunRow key={r.id} run={r} />
          ))}
        </div>
      )}
    </Section>
  );
}
