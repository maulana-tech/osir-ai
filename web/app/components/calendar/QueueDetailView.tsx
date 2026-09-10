"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { QueueDetail } from "@/lib/types.calendar";

export function QueueDetailView({ workspaceId, data }: { workspaceId: string; data: QueueDetail }) {
  const { run, busy, Feedback } = useAction();
  const [order, setOrder] = useState(data.entries.map((e) => e.id));
  const [dragging, setDragging] = useState<string | null>(null);
  const base = `/api/web/workspaces/${workspaceId}/calendar/queues/${data.queue.id}`;
  const byId = Object.fromEntries(data.entries.map((e) => [e.id, e]));
  const changed = order.join() !== data.entries.map((e) => e.id).join();

  return (
    <Section title={`${data.queue.account.name} · ${data.queue.account.platform.replace("_", " ")}`} hint={`${data.entries.length} queued`}>
      <p className="mb-3 text-xs" style={{ color: "var(--muted)" }}>
        Drag to reorder: the set of slot times stays the same, posts swap places. Gaps stay open until a post is added or moved into them.
      </p>
      {data.entries.length === 0 ? (
        <Empty>Nothing queued. Use “Next available slot” in the composer.</Empty>
      ) : (
        <ol className="space-y-1">
          {order.map((id, i) => {
            const e = byId[id];
            if (!e) return null;
            return (
              <li
                key={id}
                draggable
                onDragStart={() => setDragging(id)}
                onDragOver={(ev) => ev.preventDefault()}
                onDrop={() => {
                  if (!dragging || dragging === id) return;
                  const n = order.filter((x) => x !== dragging);
                  n.splice(i, 0, dragging);
                  setOrder(n);
                  setDragging(null);
                }}
                className="flex cursor-grab items-center gap-3 rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: "var(--line)", opacity: dragging === id ? 0.5 : 1 }}
              >
                <span className="w-6 text-xs tabular-nums" style={{ color: "var(--muted)" }}>
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <Link href={`/w/${workspaceId}/compose/${e.post_id}`} className="block truncate font-semibold hover:underline">
                    {e.title || e.caption || "(no caption)"}
                  </Link>
                  <div className="text-xs" style={{ color: "var(--muted)" }}>
                    {e.slot ? new Date(e.slot).toLocaleString() : "no slot"} · {e.status.replace(/_/g, " ")}
                    {e.author && ` · ${e.author}`}
                  </div>
                </div>
                <button className="btn" disabled={busy} title="Move to the queue's next open slot" onClick={() => run(() => call(`${base}/entries/${e.id}/reslot`, { method: "POST" }), "Moved")}>
                  Next open slot
                </button>
                <button className="btn btn-bad" disabled={busy} onClick={() => run(() => call(`${base}/entries/${e.id}`, { method: "DELETE" }), "Removed")}>
                  Remove
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {changed && (
        <div className="mt-3 flex justify-end gap-2">
          <button className="btn" onClick={() => setOrder(data.entries.map((e) => e.id))}>
            Reset
          </button>
          <button className="btn btn-accent" disabled={busy} onClick={() => run(() => call(`${base}/reorder`, { method: "POST", body: JSON.stringify({ entry_ids: order }) }), "Reordered")}>
            Save order
          </button>
        </div>
      )}
      <Feedback />
    </Section>
  );
}
