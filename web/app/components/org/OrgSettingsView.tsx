"use client";

import { useState } from "react";
import { Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Org } from "@/lib/types.admin";

export function OrgSettingsView({ org }: { org: Org }) {
  const general = useAction();
  const danger = useAction();
  const [name, setName] = useState(org.name);
  const [tz, setTz] = useState(org.default_timezone);
  const ro = !org.is_admin;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="General">
        <div className="space-y-3 text-sm">
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Name
            </span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} disabled={ro} />
          </label>
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Default timezone (workspaces without their own)
            </span>
            <select className="input" value={tz} onChange={(e) => setTz(e.target.value)} disabled={ro}>
              {org.timezones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </label>
          <div className="text-xs" style={{ color: "var(--muted)" }}>
            Your role: {org.role}
          </div>
          {!ro && (
            <div className="flex justify-end">
              <button className="btn btn-accent" disabled={general.busy} onClick={() => general.run(() => call("/api/web/org/", { method: "PATCH", body: JSON.stringify({ name, default_timezone: tz }) }), "Saved")}>
                Save
              </button>
            </div>
          )}
          <general.Feedback />
        </div>
      </Section>

      {org.is_owner && (
        <Section title="Danger zone">
          {org.deletion_scheduled_for ? (
            <div className="space-y-3 text-sm">
              <p style={{ color: "var(--bad)" }}>
                Deletion scheduled for {new Date(org.deletion_scheduled_for).toLocaleString()}. Everything in this organization will be removed then.
              </p>
              <div className="flex flex-wrap gap-2">
                <button className="btn" disabled={danger.busy} onClick={() => danger.run(() => call("/api/web/org/delete/cancel", { method: "POST" }), "Deletion cancelled")}>
                  Cancel deletion
                </button>
                <button
                  className="btn btn-bad"
                  disabled={danger.busy}
                  onClick={async () => {
                    if (!window.confirm("Delete the organization right now? This cannot be undone.")) return;
                    const r = await danger.run(() => call<{ redirect: string }>("/api/web/org/delete/now", { method: "POST" }));
                    if (r) window.location.href = r.redirect;
                  }}
                >
                  Delete now
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <p style={{ color: "var(--muted)" }}>Scheduling a deletion gives you 14 days to change your mind. Members keep access until then.</p>
              <button className="btn btn-bad" disabled={danger.busy} onClick={() => window.confirm(`Schedule "${org.name}" for deletion in 14 days?`) && danger.run(() => call("/api/web/org/delete", { method: "POST" }), "Deletion scheduled")}>
                Schedule deletion
              </button>
            </div>
          )}
          <danger.Feedback />
        </Section>
      )}
    </div>
  );
}
