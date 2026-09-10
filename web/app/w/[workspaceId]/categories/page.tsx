import { CategoriesView } from "@/app/components/create/CategoriesView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Category } from "@/lib/types.composer";

export const dynamic = "force-dynamic";

export default async function CategoriesPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const { categories } = await studio<{ categories: Category[] }>(`/api/web/workspaces/${workspaceId}/composer/categories`);
  return (
    <div>
      <PageHeader title="Content categories" />
      <CategoriesView workspaceId={workspaceId} categories={categories} />
    </div>
  );
}
