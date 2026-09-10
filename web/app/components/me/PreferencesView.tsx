"use client";

import { useState } from "react";
import { Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Preferences } from "@/lib/types.admin";

export function PreferencesView({ data }: { data: Preferences }) {
  const { run, busy, Feedback } = useAction();
  const [matrix, setMatrix] = useState(data.matrix);
  const [quiet, setQuiet] = useState(data.quiet_hours);
  const channels = matrix[0]?.channels.map((c) => ({ channel: c.channel, label: c.label })) ?? [];

  const flip = (event: string, channel: string) =>
    setMatrix((m) => m.map((row) => (row.event_type !== event ? row : { ...row, channels: row.channels.map((c) => (c.channel === channel ? { ...c, enabled: !c.enabled } : c)) })));

  const save = () =>
    run(
      () =>
        call("/api/web/me/notification-preferences", {
          method: "PUT",
          body: JSON.stringify({
            toggles: matrix.flatMap((row) => row.channels.map((c) => ({ event_type: row.event_type, channel: c.channel, enabled: c.enabled }))),
            quiet_hours: quiet,
          }),
        }),
      "Preferences saved",
    );

  return (
    <div className="space-y-6">
      <Section title="What to send where">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs" style={{ color: "var(--muted)" }}>
                <th className="py-1 pr-3 font-medium">Event</th>
                {channels.map((c) => (
                  <th key={c.channel} className="py-1 pr-3 text-center font-medium">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.map((row) => (
                <tr key={row.event_type} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="py-2 pr-3">{row.label}</td>
                  {row.channels.map((c) => (
                    <td key={c.channel} className="py-2 pr-3 text-center">
                      <input type="checkbox" checked={c.enabled} onChange={() => flip(row.event_type, c.channel)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Quiet hours">
        <div className="space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={quiet.is_enabled} onChange={(e) => setQuiet({ ...quiet, is_enabled: e.target.checked })} />
            Hold email and push notifications during quiet hours
          </label>
          <div className="flex flex-wrap items-end gap-3" style={{ opacity: quiet.is_enabled ? 1 : 0.5 }}>
            <label className="block">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                From
              </span>
              <input className="input w-auto" type="time" value={quiet.start_time} disabled={!quiet.is_enabled} onChange={(e) => setQuiet({ ...quiet, start_time: e.target.value })} />
            </label>
            <label className="block">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                To
              </span>
              <input className="input w-auto" type="time" value={quiet.end_time} disabled={!quiet.is_enabled} onChange={(e) => setQuiet({ ...quiet, end_time: e.target.value })} />
            </label>
            <label className="block">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                Timezone
              </span>
              <input className="input w-auto" value={quiet.timezone} disabled={!quiet.is_enabled} onChange={(e) => setQuiet({ ...quiet, timezone: e.target.value })} placeholder="UTC" />
            </label>
            <label className="flex items-center gap-2 pb-2">
              <input type="checkbox" checked={quiet.digest_mode} disabled={!quiet.is_enabled} onChange={(e) => setQuiet({ ...quiet, digest_mode: e.target.checked })} />
              Send one digest afterwards
            </label>
          </div>
        </div>
      </Section>

      <div className="flex justify-end">
        <button className="btn btn-accent" disabled={busy} onClick={save}>
          Save preferences
        </button>
      </div>
      <Feedback />
    </div>
  );
}
