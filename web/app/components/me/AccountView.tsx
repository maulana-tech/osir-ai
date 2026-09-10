"use client";

import { useState } from "react";
import { Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Profile } from "@/lib/types.admin";

export function AccountView({ profile }: { profile: Profile }) {
  const nameAct = useAction();
  const pwAct = useAction();
  const avatarAct = useAction();
  const delAct = useAction();
  const [name, setName] = useState(profile.name);
  const [pw, setPw] = useState({ current_password: "", password: "", password_confirm: "" });

  async function uploadAvatar(file: File | null, remove = false) {
    const fd = new FormData();
    if (file) fd.append("avatar", file);
    if (remove) fd.append("remove", "true");
    const csrf = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] ?? "";
    const res = await fetch("/api/web/me/account/avatar", { method: "POST", body: fd, headers: { "X-CSRFToken": decodeURIComponent(csrf) } });
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail ?? "Upload failed");
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Profile">
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-3">
            {profile.avatar_url ? <img src={profile.avatar_url} alt="" className="h-12 w-12 rounded-full object-cover" /> : <div className="flex h-12 w-12 items-center justify-center rounded-full border font-semibold" style={{ borderColor: "var(--line)" }}>{profile.display_name.slice(0, 1)}</div>}
            <label className="btn cursor-pointer">
              Upload photo
              <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && avatarAct.run(() => uploadAvatar(e.target.files![0]), "Photo updated")} />
            </label>
            {profile.avatar_url && (
              <button className="btn" onClick={() => avatarAct.run(() => uploadAvatar(null, true), "Photo removed")}>
                Remove
              </button>
            )}
          </div>
          <avatarAct.Feedback />
          <label className="block">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Name
            </span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="text-xs" style={{ color: "var(--muted)" }}>
            {profile.email}
            {profile.organization && ` · ${profile.organization.name} (${profile.organization.role})`} · member since {new Date(profile.created_at).toLocaleDateString()}
          </div>
          <div className="flex justify-end">
            <button className="btn btn-accent" disabled={nameAct.busy || !name.trim()} onClick={() => nameAct.run(() => call("/api/web/me/account", { method: "PATCH", body: JSON.stringify({ name }) }), "Saved")}>
              Save
            </button>
          </div>
          <nameAct.Feedback />
        </div>
      </Section>

      <Section title="Security">
        <div className="space-y-3 text-sm">
          <div className="text-xs" style={{ color: "var(--muted)" }}>
            Two-factor authentication: {profile.totp_enabled ? "on" : "off"} ·{" "}
            <a href={profile.totp_enabled ? "/accounts/2fa/disable/" : "/accounts/2fa/setup/"} className="underline">
              {profile.totp_enabled ? "disable" : "set up"}
            </a>
          </div>
          <input className="input" type="password" placeholder="Current password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
          <input className="input" type="password" placeholder="New password" autoComplete="new-password" value={pw.password} onChange={(e) => setPw({ ...pw, password: e.target.value })} />
          <input className="input" type="password" placeholder="Confirm new password" autoComplete="new-password" value={pw.password_confirm} onChange={(e) => setPw({ ...pw, password_confirm: e.target.value })} />
          <div className="flex justify-end">
            <button
              className="btn btn-accent"
              disabled={pwAct.busy || !pw.current_password || !pw.password}
              onClick={() =>
                pwAct.run(async () => {
                  await call("/api/web/me/account/password", { method: "POST", body: JSON.stringify(pw) });
                  setPw({ current_password: "", password: "", password_confirm: "" });
                }, "Password changed")
              }
            >
              Change password
            </button>
          </div>
          <pwAct.Feedback />
        </div>
      </Section>

      <Section title="Danger zone">
        <div className="space-y-2 text-sm">
          {profile.sole_owner_of.length > 0 ? (
            <p style={{ color: "var(--muted)" }}>You are the only owner of {profile.sole_owner_of.join(", ")}. Transfer ownership or delete the organization first.</p>
          ) : (
            <p style={{ color: "var(--muted)" }}>Deleting your account removes your memberships and signs you out. Content you created stays with the organization.</p>
          )}
          <button
            className="btn btn-bad"
            disabled={delAct.busy || profile.sole_owner_of.length > 0}
            onClick={async () => {
              if (!window.confirm("Delete your account? This cannot be undone.")) return;
              const r = await delAct.run(() => call<{ redirect: string }>("/api/web/me/account", { method: "DELETE" }));
              if (r) window.location.href = r.redirect;
            }}
          >
            Delete my account
          </button>
          <delAct.Feedback />
        </div>
      </Section>
    </div>
  );
}
