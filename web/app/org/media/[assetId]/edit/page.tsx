import { AssetEditor } from "@/app/components/media/AssetEditor";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { AssetDetail } from "@/lib/types.media";

export const dynamic = "force-dynamic";

export default async function EditSharedAssetPage({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  const { asset } = await studio<AssetDetail>(`/api/web/org/media/${assetId}`);
  return (
    <div>
      <PageHeader title={`Edit ${asset.filename}`} />
      <AssetEditor asset={asset} scope={{ apiBase: "/api/web/org/media", pageBase: "/org/media", shared: true, canUpload: true, canEdit: true, canDelete: false, canManageFolders: false }} />
    </div>
  );
}
