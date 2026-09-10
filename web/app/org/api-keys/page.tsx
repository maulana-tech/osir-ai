import { ApiKeysView } from "@/app/components/org/ApiKeysView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { ApiKeys } from "@/lib/types.admin";

export const dynamic = "force-dynamic";

export default async function ApiKeysPage({ searchParams }: { searchParams: Promise<{ show?: string }> }) {
  const { show } = await searchParams;
  const data = await studio<ApiKeys>(`/api/web/org/api-keys${show === "all" ? "?show=all" : ""}`);
  return (
    <div>
      <PageHeader title="API keys" />
      <ApiKeysView data={data} showAll={show === "all"} />
    </div>
  );
}
