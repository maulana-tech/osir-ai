export type RunStatus = "pending" | "running" | "succeeded" | "failed";
export type Task = "inbox" | "calendar" | "digest" | "command";

export interface Action {
  kind: string;
  target_id?: string;
  summary: string;
}

export interface RunReport {
  task?: string;
  dry_run?: boolean;
  actions?: Action[];
  decisions_for_humans?: string[];
  notes?: string;
}

export interface AgentRun {
  id: string;
  task: Task;
  status: RunStatus;
  dry_run: boolean;
  instruction: string;
  triggered_by: string | null;
  report: RunReport;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Decision {
  id: string;
  event_type: "agent_decision_needed" | "agent_digest";
  title: string;
  body: string;
  data: { post_id?: string; message_id?: string; kind?: string; workspace_id?: string };
  is_read: boolean;
  created_at: string;
}

export type Autonomy = "off" | "draft_only" | "autopilot";

export interface Policy {
  workspace_id: string;
  workspace_name: string;
  timezone: string;
  agent_autonomy: Autonomy;
  autonomy_levels: Autonomy[];
  approval_workflow_mode: string;
  direct_scheduling_allowed: boolean;
  can_publish: boolean;
  can_change_policy: boolean;
  agentcore_configured: boolean;
}

export interface PlatformPostSummary {
  id: string;
  social_account_id: string;
  platform: string;
  account_name?: string;
  status: string;
  scheduled_at: string | null;
}

export interface Post {
  id: string;
  title: string;
  caption: string;
  first_comment: string;
  status: string;
  scheduled_at: string | null;
  published_at: string | null;
  proposed_publish_at: string | null;
  platform_posts: PlatformPostSummary[];
  created_at: string;
  updated_at: string;
}

// --- app shell ---------------------------------------------------------------

export interface WorkspaceSummary {
  id: string;
  name: string;
  role: string;
  timezone: string;
  agent_autonomy: Autonomy;
  approval_workflow_mode: string;
  permissions: string[];
}

export interface Me {
  user: {
    id: string;
    email: string;
    name: string;
    avatar_url: string;
    tos_accepted: boolean;
    totp_enabled: boolean;
  };
  organization: { id: string; name: string; role: string; can_create_workspace: boolean } | null;
  current_workspace_id: string | null;
  workspaces: WorkspaceSummary[];
}

export interface Channel {
  id: string;
  platform: string;
  platform_label: string;
  name: string;
  handle: string;
  avatar_url: string;
  connection_status: string;
  last_error: string;
  queued_post_count: number;
  auth_source: string;
}

export interface Sidebar {
  channels: Channel[];
  unhealthy_channels: Channel[];
  connectable_platforms: { platform: string; label: string }[];
  analytics_enabled_platforms: string[];
  unread_inbox_count: number;
  pending_approvals: number;
}
