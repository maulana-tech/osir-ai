export interface Derived {
  value: number;
  delta: number;
  series: number[];
  kind: "count" | "percent" | "minutes" | string;
}

export interface MetricCard {
  metric: string;
  label: string;
  derived: Derived;
}

export interface AnalyticsAccount {
  id: string;
  platform: string;
  platform_label: string;
  name: string;
  avatar_url: string;
  follower_count: number;
  analytics_available: boolean;
  unavailable_reason: string | null;
  disabled_by_admin: boolean;
  needs_reconnect: boolean;
}

export interface PostRow {
  platform_post_id: string;
  post_id: string;
  caption: string;
  date: string;
  days_ago: number | null;
  media_kind: string;
  media_preview: { url: string; kind?: string } | null;
  stats: Record<string, number>;
}

export interface PostTable {
  metrics: string[];
  metric_labels: { key: string; label: string; kind: string }[];
  media_kinds: string[];
  type_filter: string;
  rows: PostRow[];
  total: number;
  page: number;
  total_pages: number;
  page_from: number;
  page_to: number;
  sort_key: string;
  sort_dir: string;
  toggled_dir: string;
  days_filter: number | null;
  primary: string;
}

export interface AccountAnalytics {
  account: AnalyticsAccount;
  accounts: AnalyticsAccount[];
  days: number;
  range_choices: number[];
  is_fresh: boolean;
  follower_growth?: Derived | null;
  hero_cards?: MetricCard[];
  engagement?: { rate: Derived; parts: MetricCard[] } | null;
  chart?: { metric: string; label: string; chips: { key: string; label: string }[]; derived: Derived; labels: string[] };
  table?: PostTable;
}

export interface AnalyticsIndex {
  enabled: boolean;
  accounts: AnalyticsAccount[];
  preferred_account_id: string | null;
}

export interface PostDetail {
  id: string;
  post_id: string;
  account: { id: string; name: string; handle: string; platform: string; avatar_url: string };
  caption: string;
  date: string;
  days_ago: number | null;
  media_kind: string;
  media_preview: { url: string; kind: string } | null;
  captured_at: string | null;
  platform_post_id: string;
  metric_tiles: { key: string; label: string; value: number; kind: string; sparkline: number[]; is_primary: boolean }[];
}
