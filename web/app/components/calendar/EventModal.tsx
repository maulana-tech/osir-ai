"use client";

import { useState } from "react";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { CalendarEvent } from "@/lib/types.calendar";

export function EventModal({ workspaceId, event, onClose }: { workspaceId: string; event: Partial<CalendarEvent>; onClose: () => void }) {
  const { run, busy, Feedback } = useAction();
  const [e, setE] = useState({ title: event.title ?? "", description: event.description ?? "", start_date: event.start_date ?? "", end_date: event.end_date ?? event.start_date ?? "", color: event.color ?? "#0a0a0a" });
  const base = `/api/web/workspaces/${workspaceId}/calendar/events`;
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }} onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl" onClick={(x) => x.stopPropagation()} role="dialog">
        <h2 className="mb-3 text-sm font-semibold">{event.id ? "Edit event" : "New calendar event"}</h2>
        <div className="space-y-2 text-sm">
          <input className="input" placeholder="Title (e.g. Product launch, Holiday)" value={e.title} autoFocus onChange={(x) => setE({ ...e, title: x.target.value })} />
          <textarea className="input" rows={2} placeholder="Notes" value={e.description} onChange={(x) => setE({ ...e, description: x.target.value })} />
          <div className="flex items-center gap-2">
            <input className="input" type="date" value={e.start_date} onChange={(x) => setE({ ...e, start_date: x.target.value, end_date: e.end_date < x.target.value ? x.target.value : e.end_date })} />
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              to
            </span>
            <input className="input" type="date" value={e.end_date} min={e.start_date} onChange={(x) => setE({ ...e, end_date: x.target.value })} />
            <input type="color" value={e.color} onChange={(x) => setE({ ...e, color: x.target.value })} className="h-9 w-9 shrink-0" title="Colour" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            {event.id && (
              <button
                className="btn btn-bad mr-auto"
                disabled={busy}
                onClick={async () => {
                  if (!window.confirm("Delete this event?")) return;
                  const r = await run(() => call(`${base}/${event.id}`, { method: "DELETE" }));
                  if (r !== undefined) onClose();
                }}
              >
                Delete
              </button>
            )}
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn btn-accent"
              disabled={busy || !e.title.trim() || !e.start_date}
              onClick={async () => {
                const r = await run(() => call(event.id ? `${base}/${event.id}` : base, { method: event.id ? "PUT" : "POST", body: JSON.stringify(e) }));
                if (r !== undefined) onClose();
              }}
            >
              Save
            </button>
          </div>
          <Feedback />
        </div>
      </div>
    </div>
  );
}
