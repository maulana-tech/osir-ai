export interface ComposerAccount {
  id: string;
  platform: string;
  name: string;
  handle: string;
  avatar_url: string;
  char_limit: number;
  escaped_chars: string;
  needs_title: boolean;
  title_max_length: number;
  title_label: string;
  caption_label: string;
  supports_first_comment: boolean;
  advanced_fields: string[];
}

export interface MediaRef {
  id: string;
  url: string;
  thumbnail_url: string | null;
  filename: string;
  media_type: string;
  width?: number;
  height?: number;
  duration?: number;
  position?: number;
  alt_text?: string;
}

export interface PlatformPostRow {
  id: string;
  social_account_id: string;
  platform: string;
  status: string;
  title: string | null;
  caption: string | null;
  first_comment: string | null;
  extra: Record<string, unknown>;
  scheduled_at: string | null;
  publish_error: string;
  first_comment_status: string;
  first_comment_error: string;
  platform_post_id: string;
}

export interface ComposerPost {
  id: string;
  title: string;
  caption: string;
  first_comment: string;
  internal_notes: string;
  tags: string[];
  category_id: string | null;
  status: string;
  scheduled_at: string | null;
  proposed_publish_at: string | null;
  scheduled_date: string;
  scheduled_time: string;
  schedule_is_proposed: boolean;
  is_committed: boolean;
  read_only: boolean;
  can_edit: boolean;
  author: string | null;
  updated_at: string;
  platform_posts: PlatformPostRow[];
  media: MediaRef[];
  approval_history: { action: string; user: string | null; comment: string; created_at: string }[];
  latest_feedback: { action: string; comment: string } | null;
  show_submit: boolean;
  show_resubmit: boolean;
  versions_count: number;
  recurrence: { frequency: string; interval: number; end_date: string } | null;
}

export interface ComposerContext {
  workspace: {
    id: string;
    name: string;
    timezone: string;
    approval_workflow_mode: string;
    default_first_comment: string;
    default_hashtags: string[];
  };
  accounts: ComposerAccount[];
  categories: { id: string; name: string; color: string }[];
  tags: string[];
  queues: { id: string; name: string; social_account_id: string; account_name: string; platform: string }[];
  perms: { publish_directly: boolean; approve_posts: boolean; edit_others_posts: boolean; view_internal_notes: boolean };
  unsplash_enabled: boolean;
  account_scope: string;
  initial: { scheduled_date?: string; scheduled_time?: string; template?: { caption?: string; tags?: string[]; first_comment?: string }; selected_accounts?: string[] };
  post: ComposerPost | null;
}

export interface SaveResult {
  id: string;
  status: string;
  scheduled_at: string | null;
  proposed_publish_at: string | null;
  platform_statuses: Record<string, string>;
  updated_at: string;
}

export interface Idea {
  id: string;
  title: string;
  description: string;
  tags: string[];
  group_id: string | null;
  position: number;
  author: string | null;
  post_id: string | null;
  media: { asset_id: string; url: string; thumbnail_url: string | null; filename: string; media_type: string; position: number }[];
  updated_at: string;
}

export interface Board {
  columns: { id: string; name: string; ideas: Idea[] }[];
  tags: string[];
  active_tag: string;
}

export interface BuiltinTemplate {
  id: number;
  emoji: string;
  title: string;
  description: string;
  category: string;
  color?: string;
  body?: string;
  tags?: string[];
}

export interface Templates {
  categories: { slug: string; label: string; icon: string }[];
  featured_ids: number[];
  builtin: BuiltinTemplate[];
  saved: { id: string; name: string; description: string; template_data: Record<string, unknown>; created_by: string | null; created_at: string }[];
}

export interface FeedRow {
  id: string;
  name: string;
  url: string;
  website_url: string;
  favicon_url: string;
}

export interface FeedEvent {
  event_id: string;
  feed_id: string;
  feed_name: string;
  feed_favicon_url: string;
  feed_website_url: string;
  title: string;
  link: string;
  summary: string;
  image_url: string;
  published_at: string | null;
}

export interface FeedsData {
  feeds: FeedRow[];
  selected_feed_id: string;
  events: FeedEvent[];
  next_offset: number;
  has_more: boolean;
  total: number;
  last_refreshed_at: string | null;
}

export interface Explore {
  categories: { slug: string; label: string }[];
  active_category: string;
  curated_feeds: { name: string; rss: string; website: string; description?: string; favicon: string; subscribed: boolean }[];
}

export interface Category {
  id: string;
  name: string;
  color: string;
  position: number;
}
