export interface ChannelAccount {
  id: string;
  platform: string;
  platform_label: string;
  name: string;
  handle: string;
  avatar_url: string;
  follower_count: number;
  connection_status: string;
  needs_reconnect: boolean;
  last_error: string;
  last_health_check_at: string | null;
  webhooks_active: boolean | null;
  webhook_needs_reconnect: boolean;
  webhook_error: string;
  analytics_needs_reconnect: boolean;
  auth_source: string;
  connected_at: string;
}

export interface Channels {
  accounts: ChannelAccount[];
  platforms: { platform: string; label: string; configured: boolean; via_composio: boolean }[];
  platform_labels: Record<string, string>;
  can_manage: boolean;
}

export interface WorkspaceSettings {
  id: string;
  name: string;
  description: string;
  icon_url: string;
  timezone: string;
  effective_timezone: string;
  is_archived: boolean;
  approval_workflow_mode: string;
  approval_modes: { value: string; label: string }[];
  agent_autonomy: string;
  autonomy_levels: { value: string; label: string }[];
  is_owner_or_manager: boolean;
  can_archive: boolean;
  can_delete: boolean;
  timezones: string[];
}

export interface Clients {
  clients: { membership_id: string; name: string; email: string; link_expires_at: string | null; link_last_used_at: string | null }[];
  pending_invites: { id: string; email: string; invited_by: string | null; expires_at: string }[];
}

export interface Checklist {
  dismissed: boolean;
  completed: number;
  total: number;
  items: { key: string; title: string; description: string; completed: boolean }[];
}

export interface Org {
  id: string;
  name: string;
  default_timezone: string;
  logo_url: string;
  role: string;
  is_owner: boolean;
  is_admin: boolean;
  deletion_requested_at: string | null;
  deletion_scheduled_for: string | null;
  timezones: string[];
}

export interface OrgWorkspaces {
  workspaces: {
    id: string;
    name: string;
    is_archived: boolean;
    member_count: number;
    members: { name: string; role: string }[];
    can_manage: boolean;
    is_member: boolean;
  }[];
  can_create: boolean;
}

export interface Members {
  members: {
    membership_id: string;
    user_id: string;
    name: string;
    email: string;
    org_role: string;
    joined_at: string | null;
    workspaces: { id: string; name: string; role: string }[];
  }[];
  pending_invites: {
    id: string;
    email: string;
    org_role: string;
    workspace_assignments: { workspace_id: string; role: string }[];
    invited_by: string | null;
    expires_at: string;
  }[];
  workspaces: { id: string; name: string }[];
  org_role_choices: { value: string; label: string }[];
  workspace_role_choices: { value: string; label: string }[];
  is_admin: boolean;
  current_user_id: string;
}

export interface ApiKeyRow {
  id: string;
  name: string;
  workspace_id: string;
  workspace_name: string;
  accounts: { id: string; name: string; platform: string }[];
  permissions: string[];
  issued_by: string | null;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  status: "active" | "revoked" | "expired";
}

export interface ApiKeys {
  keys: ApiKeyRow[];
  revoked_count: number;
  workspaces: { id: string; name: string }[];
}

export interface Profile {
  id: string;
  email: string;
  name: string;
  display_name: string;
  avatar_url: string;
  totp_enabled: boolean;
  created_at: string;
  organization: { name: string; role: string } | null;
  sole_owner_of: string[];
}

export interface NotificationRow {
  id: string;
  event_type: string;
  title: string;
  body: string;
  data: Record<string, string>;
  is_read: boolean;
  created_at: string;
}

export interface Notifications {
  notifications: NotificationRow[];
  total: number;
  page: number;
  has_next: boolean;
  unread_count: number;
  event_types: { value: string; label: string }[];
}

export interface Preferences {
  matrix: { event_type: string; label: string; channels: { channel: string; label: string; enabled: boolean }[] }[];
  quiet_hours: { is_enabled: boolean; start_time: string; end_time: string; timezone: string; digest_mode: boolean };
}
