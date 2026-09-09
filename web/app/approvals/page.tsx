import { studio } from "@/lib/studio";
import { approvePost, rejectPost } from "../actions";
import { Empty, Section, timeAgo } from "../components/ui";

export const dynamic = "force-dynamic";

export default async function Approvals() {
  const posts = await studio.approvals();
  return (
    <Section title="Waiting for approval" hint={`${posts.length} post${posts.length === 1 ? "" : "s"}`}>
      {posts.length === 0 ? (
        <Empty>Nothing to review. Drafts the agent submits will show up here.</Empty>
      ) : (
        <ul className="space-y-4">
          {posts.map((p) => (
            <li key={p.id} className="rounded-lg border p-4" style={{ borderColor: "var(--line)" }}>
              <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                {p.platform_posts.map((pp) => (
                  <span key={pp.id} className="pill">
                    {pp.platform.replace("_", " ")}
                  </span>
                ))}
                <span>updated {timeAgo(p.updated_at)}</span>
                {p.proposed_publish_at && <span>· proposed {new Date(p.proposed_publish_at).toLocaleString()}</span>}
              </div>
              {p.title && <h3 className="mt-2 font-semibold">{p.title}</h3>}
              <p className="mt-2 whitespace-pre-wrap text-sm">{p.caption}</p>
              {p.first_comment && (
                <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
                  First comment: {p.first_comment}
                </p>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <form action={approvePost}>
                  <input type="hidden" name="id" value={p.id} />
                  <button className="btn btn-ok" type="submit">
                    Approve
                  </button>
                </form>
                <form action={rejectPost} className="flex flex-1 items-center gap-2">
                  <input type="hidden" name="id" value={p.id} />
                  <input name="comment" className="input" placeholder="Why? (sent back to the drafts list)" />
                  <button className="btn btn-bad" type="submit">
                    Reject
                  </button>
                </form>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
