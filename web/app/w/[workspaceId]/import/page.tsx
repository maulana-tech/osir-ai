import { CsvImportView } from "@/app/components/create/CsvImportView";
import { PageHeader } from "@/app/components/ui";

export const dynamic = "force-dynamic";

export default async function ImportPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  return (
    <div>
      <PageHeader title="Import posts from CSV" />
      <CsvImportView workspaceId={workspaceId} />
    </div>
  );
}
