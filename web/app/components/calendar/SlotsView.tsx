"use client";

import { useState } from "react";
import { Empty, Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { SlotsData } from "@/lib/types.calendar";

export function SlotsView({ workspaceId, data, canManage }: { workspaceId: string; data: SlotsData; canManage: boolean }) {
  const { run, busy, Feedback } = useAction();
  const [draft, setDraft] = useState<{ account: string; day: number; time: string } | null>(null);
  const [editing, setEditing] = useState<{ id: string; time: string } | null>(null);
  const base = `/api/web/workspaces/${workspaceId}/calendar/slots`;
  return (
    <div className="space-y-6">
      <p className="text-xs" style={{ color: "var(--muted)" }}>
        Slots are the times each channel posts when you add to its queue or pick “next available”. Times are in {data.timezone}. Empty slots also show on the calendar as open “+” rows.
      </p>
      {data.accounts.length === 0 && <Empty>Connect a channel first.</Empty>}
      {data.accounts.map((a) => (
        <Section key={a.id} title={`${a.name} · ${a.platform.replace("_", " ")}`} hint={`${a.slots.length} slot${a.slots.length === 1 ? "" : "s"}`}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            {data.days.map((d) => {
              const slots = a.slots.filter((s) => s.day_of_week === d.value);
              const allActive = slots.length > 0 && slots.every((s) => s.is_active);
              return (
                <div key={d.value} className="rounded-lg border p-2 text-xs" style={{ borderColor: "var(--line)" }}>
                  <div className="mb-1 flex items-center justify-between font-semibold">
                    <span>{d.label}</span>
                    {canManage && slots.length > 0 && (
                      <button className="underline" style={{ color: "var(--muted)" }} title={allActive ? "Pause this day" : "Resume this day"} disabled={busy} onClick={() => run(() => call(`${base}/toggle-day`, { method: "POST", body: JSON.stringify({ social_account_id: a.id, day_of_week: d.value }) }))}>
                        {allActive ? "pause" : "resume"}
                      </button>
                    )}
                  </div>
                  <ul className="space-y-1">
                    {slots.map((s) => (
                      <li key={s.id} className="flex items-center gap-1" style={{ opacity: s.is_active ? 1 : 0.5 }}>
                        {editing?.id === s.id ? (
                          <>
                            <input className="input py-0.5" type="time" value={editing.time} onChange={(e) => setEditing({ id: s.id, time: e.target.value })} />
                            <button
                              className="btn py-0.5"
                              disabled={busy}
                              onClick={async () => {
                                const r = await run(() => call(`${base}/${s.id}`, { method: "PATCH", body: JSON.stringify({ time: editing.time }) }));
                                if (r !== undefined) setEditing(null);
                              }}
                            >
                              ok
                            </button>
                          </>
                        ) : (
                          <>
                            <span className="tabular-nums">{s.time}</span>
                            {!s.is_active && <span className="pill">paused</span>}
                            {canManage && (
                              <span className="ml-auto flex gap-1">
                                <button className="underline" onClick={() => setEditing({ id: s.id, time: s.time })}>
                                  edit
                                </button>
                                <button className="underline" style={{ color: "var(--bad)" }} disabled={busy} onClick={() => run(() => call(`${base}/${s.id}`, { method: "DELETE" }))}>
                                  ×
                                </button>
                              </span>
                            )}
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                  {canManage &&
                    (draft?.account === a.id && draft.day === d.value ? (
                      <div className="mt-1 flex items-center gap-1">
                        <input className="input py-0.5" type="time" value={draft.time} autoFocus onChange={(e) => setDraft({ ...draft, time: e.target.value })} />
                        <button
                          className="btn py-0.5"
                          disabled={busy || !draft.time}
                          onClick={async () => {
                            const r = await run(() => call(base, { method: "POST", body: JSON.stringify({ social_account_id: a.id, day_of_week: d.value, time: draft.time }) }));
                            if (r !== undefined) setDraft(null);
                          }}
                        >
                          add
                        </button>
                      </div>
                    ) : (
                      <button className="mt-1 underline" style={{ color: "var(--muted)" }} onClick={() => setDraft({ account: a.id, day: d.value, time: "09:00" })}>
                        + add
                      </button>
                    ))}
                </div>
              );
            })}
          </div>
        </Section>
      ))}
      <Feedback />
    </div>
  );
}
