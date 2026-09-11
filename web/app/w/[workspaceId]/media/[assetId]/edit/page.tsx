import { AssetEditor } from "@/app/components/media/AssetEditor";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { AssetDetail } from "@/lib/types.media";

export const dynamic = "force-dynamic";

export default async function EditAssetPage({ params }: { params: Promise<{ workspaceId: string; assetId: string }> }) {
  const { workspaceId, assetId } = await params;
  const { asset } = await studio<AssetDetail>(`/api/web/workspaces/${workspaceId}/media/${assetId}`);
  return (
    <div>
      <PageHeader title={`Edit ${asset.filename}`} />
      <AssetEditor
        asset={asset}
        scope={{ apiBase: `/api/web/workspaces/${workspaceId}/media`, pageBase: `/w/${workspaceId}/media`, shared: false, canUpload: true, canEdit: true, canDelete: false, canManageFolders: false }}
      />
    </div>
  );
}
