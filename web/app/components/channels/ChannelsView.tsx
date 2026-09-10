"use client";

import { DjangoForm } from "@/app/components/DjangoForm";
import { Empty, Section, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Channels } from "@/lib/types.admin";

const STATUS_LABEL: Record<string, string> = {
  connected: "Connected",
  token_expiring: "Token expiring",
  disconnected: "Disconnected",
  error: "Needs attention",
};

export function ChannelsView({ workspaceId, data }: { workspaceId: string; data: Channels }) {
  const { run, busy, Feedback } = useAction();
  const base = `/api/web/workspaces/${workspaceId}/channels`;
  const connectUrl = `/social-accounts/${workspaceId}/connect/`;

  return (
    <div className="space-y-6">
      <Section title="Connected accounts" hint={`${data.accounts.length}`}>
        {data.accounts.length === 0 ? (
          <Empty>No accounts yet. Connect one below.</Empty>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {data.accounts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-4 py-3">
                <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border text-xs font-bold" style={{ borderColor: "var(--line)" }}>
                  {a.avatar_url ? <img src={a.avatar_url} alt="" className="h-full w-full object-cover" /> : a.platform_label.slice(0, 2)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-semibold">{a.name || a.handle}</span>
                    <span className="pill">{a.platform_label}</span>
                    <span className={a.needs_reconnect ? "pill pill-bad" : a.connection_status === "connected" ? "pill pill-ok" : "pill"}>
                      {STATUS_LABEL[a.connection_status] ?? a.connection_status}
                    </span>
                    {a.auth_source === "composio" && <span className="pill">via Composio</span>}
                  </div>
                  <div className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>
                    {a.handle && <span>@{a.handle} · </span>}
                    {a.follower_count.toLocaleString()} followers · connected {timeAgo(a.connected_at)}
                    {a.last_health_check_at && <span> · checked {timeAgo(a.last_health_check_at)}</span>}
                  </div>
                  {a.last_error && (
                    <div className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
                      {a.last_error}
                    </div>
                  )}
                  {a.webhooks_active === false && !a.needs_reconnect && (
                    <div className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
                      Real-time updates are off{a.webhook_error ? `: ${a.webhook_error}` : "."}{" "}
                      {data.can_manage && (
                        <button className="underline" disabled={busy} onClick={() => run(() => call(`${base}/${a.id}/retry-webhooks`, { method: "POST" }), "Retried")}>
                          retry
                        </button>
                      )}
                    </div>
                  )}
                  {a.analytics_needs_reconnect && (
                    <div className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
                      Reconnect to grant analytics permissions.
                    </div>
                  )}
                </div>
                {data.can_manage && (
                  <div className="flex shrink-0 items-center gap-2">
                    <DjangoForm action={`/social-accounts/${workspaceId}/${a.id}/reconnect/`}>
                      <button className="btn" type="submit">
                        Reconnect
                      </button>
                    </DjangoForm>
                    <button
                      className="btn btn-bad"
                      disabled={busy}
                      onClick={() => {
                        if (window.confirm(`Disconnect ${a.name || a.handle}? Posts that only target this account will be deleted.`)) {
                          void run(() => call(`${base}/${a.id}/disconnect`, { method: "POST" }), "Disconnected");
                        }
                      }}
                    >
                      Disconnect
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        <Feedback />
      </Section>

      {data.can_manage && (
        <Section title="Connect a channel">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.platforms.map((p) => {
              const ready = p.configured || p.via_composio;
              return (
                <div key={p.platform} className="rounded-lg border p-4" style={{ borderColor: "var(--line)", opacity: ready ? 1 : 0.6 }}>
                  <div className="text-sm font-semibold">{p.label}</div>
                  <div className="mb-3 text-xs" style={{ color: "var(--muted)" }}>
                    {p.configured ? "Your developer app" : p.via_composio ? "Sign in through Composio" : "No developer app configured"}
                  </div>
                  {ready ? (
                    <DjangoForm action={connectUrl} fields={{ platform: p.platform }}>
                      <button className="btn btn-accent w-full justify-center" type="submit">
                        {p.via_composio && !p.configured ? "Connect via Composio" : "Connect"}
                      </button>
                    </DjangoForm>
                  ) : (
                    <span className="btn w-full justify-center" style={{ cursor: "not-allowed" }}>
                      Not configured
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}
    </div>
  );
}
