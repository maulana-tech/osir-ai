import { MediaLibrary } from "@/app/components/media/MediaLibrary";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Library } from "@/lib/types.media";

export const dynamic = "force-dynamic";

const KEYS = ["q", "type", "folder", "starred", "sort", "page"] as const;

export default async function MediaPage({ params, searchParams }: { params: Promise<{ workspaceId: string }>; searchParams: Promise<Record<string, string | undefined>> }) {
  const { workspaceId } = await params;
  const q = await searchParams;
  const query = new URLSearchParams();
  for (const k of KEYS) if (q[k]) query.set(k, q[k]!);
  const data = await studio<Library>(`/api/web/workspaces/${workspaceId}/media?${query}`);
  const can = data.can!;
  return (
    <div>
      <PageHeader title="Media library" />
      <MediaLibrary
        data={data}
        scope={{
          apiBase: `/api/web/workspaces/${workspaceId}/media`,
          pageBase: `/w/${workspaceId}/media`,
          shared: false,
          canUpload: can.upload_media,
          canEdit: can.edit_media,
          canDelete: can.delete_media,
          canManageFolders: can.manage_media,
        }}
      />
    </div>
  );
}
