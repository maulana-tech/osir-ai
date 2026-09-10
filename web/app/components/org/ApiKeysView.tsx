"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Empty, Section, timeAgo } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { ApiKeyRow, ApiKeys } from "@/lib/types.admin";

type Options = { accounts: { id: string; name: string; platform: string }[]; permissions: { key: string; label: string }[] };

function ScopeForm({
  workspaceId,
  initial,
  onSubmit,
  busy,
  submitLabel,
}: {
  workspaceId: string;
  initial?: { accounts: string[]; permissions: string[]; expires_at: string | null };
  onSubmit: (v: { social_account_ids: string[]; permissions: string[]; expires_at: string | null }) => void;
  busy: boolean;
  submitLabel: string;
}) {
  const [opts, setOpts] = useState<Options | null>(null);
  const [accounts, setAccounts] = useState<string[]>(initial?.accounts ?? []);
  const [perms, setPerms] = useState<string[]>(initial?.permissions ?? []);
  const [expires, setExpires] = useState(initial?.expires_at ? initial.expires_at.slice(0, 10) : "");
  const [err, setErr] = useState("");

  useEffect(() => {
    setOpts(null);
    call<Options>(`/api/web/org/api-keys/options?workspace_id=${workspaceId}`)
      .then((o) => {
        setOpts(o);
        if (!initial) {
          setAccounts(o.accounts.map((a) => a.id));
          setPerms(o.permissions.map((p) => p.key));
        }
      })
      .catch((e) => setErr(e.message));
  }, [workspaceId, initial]);

  if (err) return <p className="text-sm" style={{ color: "var(--bad)" }}>{err}</p>;
  if (!opts) return <p className="text-sm" style={{ color: "var(--muted)" }}>Loading…</p>;
  const toggle = (list: string[], set: (v: string[]) => void, id: string) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="mb-1 text-xs" style={{ color: "var(--muted)" }}>
          Accounts the key may act on
        </div>
        {opts.accounts.length === 0 && <p className="text-xs">No connected accounts in this workspace.</p>}
        <div className="grid gap-1 sm:grid-cols-2">
          {opts.accounts.map((a) => (
            <label key={a.id} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={accounts.includes(a.id)} onChange={() => toggle(accounts, setAccounts, a.id)} />
              {a.name} <span style={{ color: "var(--muted)" }}>{a.platform}</span>
            </label>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-1 text-xs" style={{ color: "var(--muted)" }}>
          Permissions (never more than yours)
        </div>
        <div className="grid gap-1 sm:grid-cols-2">
          {opts.permissions.map((p) => (
            <label key={p.key} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={perms.includes(p.key)} onChange={() => toggle(perms, setPerms, p.key)} />
              {p.label}
            </label>
          ))}
        </div>
      </div>
      <label className="block">
        <span className="text-xs" style={{ color: "var(--muted)" }}>
          Expires (optional)
        </span>
        <input className="input w-auto" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
      </label>
      <div className="flex justify-end">
        <button className="btn btn-accent" disabled={busy || accounts.length === 0} onClick={() => onSubmit({ social_account_ids: accounts, permissions: perms, expires_at: expires || null })}>
          {submitLabel}
        </button>
      </div>
    </div>
  );
}

function KeyRow({ k }: { k: ApiKeyRow }) {
  const { run, busy, Feedback } = useAction();
  const [editing, setEditing] = useState(false);
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{k.name}</span>
            <span className={k.status === "active" ? "pill pill-ok" : k.status === "expired" ? "pill" : "pill pill-bad"}>{k.status}</span>
          </div>
          <div className="text-xs" style={{ color: "var(--muted)" }}>
            {k.workspace_name} · {k.accounts.map((a) => a.name).join(", ") || "no accounts"} · {k.permissions.length} permission{k.permissions.length === 1 ? "" : "s"}
            {k.issued_by && ` · issued by ${k.issued_by}`} · {timeAgo(k.created_at)}
            {k.last_used_at ? ` · last used ${timeAgo(k.last_used_at)}` : " · never used"}
            {k.expires_at && ` · expires ${new Date(k.expires_at).toLocaleDateString()}`}
          </div>
        </div>
        {k.status === "active" && (
          <>
            <button className="btn" onClick={() => setEditing((v) => !v)}>
              {editing ? "Close" : "Edit"}
            </button>
            <button className="btn btn-bad" disabled={busy} onClick={() => window.confirm(`Revoke "${k.name}"? Anything using it stops working immediately.`) && run(() => call(`/api/web/org/api-keys/${k.id}/revoke`, { method: "POST" }), "Revoked")}>
              Revoke
            </button>
          </>
        )}
      </div>
      {editing && (
        <div className="mt-3 rounded-lg border p-3" style={{ borderColor: "var(--line)" }}>
          <ScopeForm
            workspaceId={k.workspace_id}
            initial={{ accounts: k.accounts.map((a) => a.id), permissions: k.permissions, expires_at: k.expires_at }}
            busy={busy}
            submitLabel="Save scope"
            onSubmit={async (v) => {
              const r = await run(() => call(`/api/web/org/api-keys/${k.id}`, { method: "PUT", body: JSON.stringify(v) }), "Scope saved");
              if (r !== undefined) setEditing(false);
            }}
          />
        </div>
      )}
      <Feedback />
    </li>
  );
}

export function ApiKeysView({ data, showAll }: { data: ApiKeys; showAll: boolean }) {
  const issue = useAction();
  const [name, setName] = useState("");
  const [wsId, setWsId] = useState(data.workspaces[0]?.id ?? "");
  const [token, setToken] = useState<{ name: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);

  return (
    <div className="space-y-6">
      {token && (
        <div className="panel p-5" style={{ borderColor: "#0a0a0a" }}>
          <div className="mb-2 text-sm font-semibold">Key “{token.name}” issued. Copy it now: it will not be shown again.</div>
          <div className="flex flex-wrap items-center gap-2">
            <code className="input flex-1 overflow-x-auto font-mono text-xs">{token.token}</code>
            <button
              className="btn"
              onClick={() =>
                navigator.clipboard.writeText(token.token).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                })
              }
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <button className="btn" onClick={() => setToken(null)}>
              Done
            </button>
          </div>
          <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
            Use it as <code>Authorization: Bearer …</code> against <code>/api/v1/</code>, or as the autopilot&apos;s <code>STUDIO_API_KEY</code>.
          </p>
        </div>
      )}

      <Section title={showAll ? "All keys" : "Active keys"} hint={`${data.keys.length}`}>
        {data.keys.length === 0 ? <Empty>No API keys yet.</Empty> : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {data.keys.map((k) => (
              <KeyRow key={k.id} k={k} />
            ))}
          </ul>
        )}
        {data.revoked_count > 0 && (
          <div className="mt-3 text-xs">
            <Link href={showAll ? "/org/api-keys" : "/org/api-keys?show=all"} className="underline" style={{ color: "var(--muted)" }}>
              {showAll ? "Hide revoked keys" : `Show ${data.revoked_count} revoked key${data.revoked_count === 1 ? "" : "s"}`}
            </Link>
          </div>
        )}
      </Section>

      {data.workspaces.length > 0 && (
        <Section title="Issue a key">
          <div className="mb-3 flex flex-wrap gap-2 text-sm">
            <input className="input flex-1" placeholder="Key name, e.g. Osir autopilot" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
            <select className="input w-auto" value={wsId} onChange={(e) => setWsId(e.target.value)}>
              {data.workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
          {wsId && (
            <ScopeForm
              key={wsId}
              workspaceId={wsId}
              busy={issue.busy || !name.trim()}
              submitLabel="Issue key"
              onSubmit={async (v) => {
                const r = await issue.run(() => call<{ key: ApiKeyRow; token: string }>("/api/web/org/api-keys", { method: "POST", body: JSON.stringify({ name, workspace_id: wsId, ...v }) }));
                if (r) {
                  setToken({ name: r.key.name, token: r.token });
                  setName("");
                }
              }}
            />
          )}
          <issue.Feedback />
        </Section>
      )}
    </div>
  );
}
