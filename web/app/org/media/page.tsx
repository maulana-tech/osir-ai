import { MediaLibrary } from "@/app/components/media/MediaLibrary";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { Library } from "@/lib/types.media";

export const dynamic = "force-dynamic";

export default async function SharedMediaPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  const query = new URLSearchParams();
  for (const k of ["q", "type", "sort", "page"]) if (q[k]) query.set(k, q[k]!);
  const data = await studio<Library>(`/api/web/org/media?${query}`);
  const admin = !!data.is_admin;
  return (
    <div>
      <PageHeader title="Shared media">
        <span className="text-xs" style={{ color: "var(--muted)" }}>
          Available in every workspace of the organization
        </span>
      </PageHeader>
      <MediaLibrary data={data} scope={{ apiBase: "/api/web/org/media", pageBase: "/org/media", shared: true, canUpload: admin, canEdit: admin, canDelete: admin, canManageFolders: false }} />
    </div>
  );
}
