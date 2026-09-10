import { ComposerView } from "@/app/components/composer/ComposerView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { ComposerContext } from "@/lib/types.composer";

export const dynamic = "force-dynamic";

const PASS = ["account", "template", "scheduled_date", "scheduled_time"] as const;

export default async function ComposePage({ params, searchParams }: { params: Promise<{ workspaceId: string }>; searchParams: Promise<Record<string, string | undefined>> }) {
  const { workspaceId } = await params;
  const q = await searchParams;
  const query = new URLSearchParams();
  for (const k of PASS) if (q[k]) query.set(k, q[k]!);
  const ctx = await studio<ComposerContext>(`/api/web/workspaces/${workspaceId}/composer/context?${query}`);
  if (q.prefill && !ctx.initial.template) ctx.initial.template = { caption: q.prefill };
  return (
    <div>
      <PageHeader title="New post" />
      <ComposerView key="new" ctx={ctx} workspaceId={workspaceId} />
    </div>
  );
}
