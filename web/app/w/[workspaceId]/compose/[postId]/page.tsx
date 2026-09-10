import { ComposerView } from "@/app/components/composer/ComposerView";
import { PageHeader } from "@/app/components/ui";
import { studio } from "@/lib/studio";
import type { ComposerContext } from "@/lib/types.composer";

export const dynamic = "force-dynamic";

export default async function EditPostPage({ params, searchParams }: { params: Promise<{ workspaceId: string; postId: string }>; searchParams: Promise<{ account?: string }> }) {
  const { workspaceId, postId } = await params;
  const { account } = await searchParams;
  const query = new URLSearchParams({ post_id: postId });
  if (account) query.set("account", account);
  const ctx = await studio<ComposerContext>(`/api/web/workspaces/${workspaceId}/composer/context?${query}`);
  const post = ctx.post!;
  return (
    <div>
      <PageHeader title={post.title || "Edit post"}>
        <span className="pill">{post.status.replace(/_/g, " ")}</span>
      </PageHeader>
      <ComposerView key={post.id} ctx={ctx} workspaceId={workspaceId} />
    </div>
  );
}
