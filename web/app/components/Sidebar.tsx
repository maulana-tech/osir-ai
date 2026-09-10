import Link from "next/link";
import type { Me, Sidebar as SidebarData, WorkspaceSummary } from "@/lib/types";
import { NavLink } from "./NavLink";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const PLATFORM_SHORT: Record<string, string> = {
  facebook: "FB",
  instagram: "IG",
  instagram_login: "IG",
  linkedin_personal: "in",
  linkedin_company: "in",
  tiktok: "TT",
  youtube: "YT",
  pinterest: "P",
  threads: "@",
  bluesky: "BS",
  google_business: "G",
  mastodon: "M",
  devto: "DEV",
};

function Badge({ n }: { n: number }) {
  if (!n) return null;
  return (
    <span className="ml-auto rounded-full px-1.5 text-[10px] font-semibold" style={{ background: "#0a0a0a", color: "#fff" }}>
      {n}
    </span>
  );
}

export function Sidebar({ me, workspace, sidebar }: { me: Me; workspace: WorkspaceSummary; sidebar: SidebarData }) {
  const base = `/w/${workspace.id}`;
  const can = (p: string) => workspace.permissions.includes(p);
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r" style={{ borderColor: "var(--line)", background: "#fafafa" }}>
      <div className="px-4 pt-5 pb-3">
        <Link href="/" className="text-base font-bold tracking-tight">
          Osir <span style={{ color: "var(--muted)" }}>AI</span>
        </Link>
      </div>

      <div className="px-3 pb-3">
        <WorkspaceSwitcher workspaces={me.workspaces} current={workspace.id} canCreate={!!me.organization?.can_create_workspace} />
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 text-sm">
        <div className="space-y-0.5">
          <NavLink href={`${base}/calendar`}>Publish</NavLink>
          {can("use_inbox") && (
            <NavLink href={`${base}/inbox`}>
              Social Inbox <Badge n={sidebar.unread_inbox_count} />
            </NavLink>
          )}
          {can("view_analytics") && sidebar.analytics_enabled_platforms.length > 0 && (
            <NavLink href={`${base}/analytics`}>Analytics</NavLink>
          )}
          <NavLink href={`${base}/approvals`}>
            Approvals <Badge n={sidebar.pending_approvals} />
          </NavLink>
          <NavLink href={`${base}/agent`}>Autopilot</NavLink>
          <NavLink href="/notifications/" external>
            Notifications
          </NavLink>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between px-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            <span>Channels</span>
            {can("manage_social_accounts") && (
              <a href={`/social-accounts/${workspace.id}/connect/`} className="hover:text-black" title="Connect a channel">
                +
              </a>
            )}
          </div>
          {sidebar.channels.length === 0 && (
            <p className="px-2 text-xs" style={{ color: "var(--muted)" }}>
              No channels yet.
            </p>
          )}
          <ul className="space-y-0.5">
            {sidebar.channels.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs">
                <span className="inline-flex h-5 w-7 items-center justify-center rounded border text-[10px] font-bold" style={{ borderColor: "var(--line)" }}>
                  {PLATFORM_SHORT[c.platform] ?? c.platform.slice(0, 2)}
                </span>
                <span className="truncate">{c.name}</span>
                {c.queued_post_count > 0 && (
                  <span className="ml-auto text-[10px]" style={{ color: "var(--muted)" }}>
                    {c.queued_post_count}
                  </span>
                )}
              </li>
            ))}
            {sidebar.unhealthy_channels.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs" style={{ color: "var(--bad)" }} title={c.last_error}>
                <span className="inline-flex h-5 w-7 items-center justify-center rounded border text-[10px] font-bold" style={{ borderColor: "var(--bad)" }}>
                  {PLATFORM_SHORT[c.platform] ?? c.platform.slice(0, 2)}
                </span>
                <span className="truncate">{c.name}</span>
                <span className="ml-auto text-[10px]">!</span>
              </li>
            ))}
          </ul>
        </div>

        {(me.organization?.role === "owner" || me.organization?.role === "admin" || can("manage_workspace_settings")) && (
          <div>
            <div className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Settings
            </div>
            <div className="space-y-0.5">
              {can("manage_workspace_settings") && (
                <NavLink href={`/workspaces/${workspace.id}/settings/`} external>
                  Workspace
                </NavLink>
              )}
              {me.organization && (
                <NavLink href="/organizations/settings/" external>
                  Organization
                </NavLink>
              )}
              <NavLink href="/members/" external>
                Team
              </NavLink>
            </div>
          </div>
        )}
      </nav>

      <div className="border-t px-4 py-3 text-xs" style={{ borderColor: "var(--line)" }}>
        <div className="truncate font-semibold">{me.user.name}</div>
        <div className="flex items-center justify-between" style={{ color: "var(--muted)" }}>
          <a href="/accounts/settings/" className="hover:text-black">
            Account
          </a>
          <form method="post" action="/accounts/logout/">
            <button type="submit" className="hover:text-black">
              Sign out
            </button>
          </form>
        </div>
      </div>
    </aside>
  );
}
