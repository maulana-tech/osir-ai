export interface Chip {
  id: string;
  post_id: string;
  at: string | null;
  status: string;
  platform: string;
  account: { id: string; name: string };
  title: string;
  caption: string;
  author: string | null;
  is_reschedulable: boolean;
  publish_error: string;
}

export interface OpenSlot {
  at: string;
  account: { id: string; name: string };
  platform: string;
  compose_date: string;
  compose_time: string;
  is_past: boolean;
}

export interface CalendarEvent {
  id: string;
  title: string;
  description: string;
  start_date: string;
  end_date: string;
  color: string;
}

export interface CalendarData {
  start: string;
  end: string;
  display_timezone: string;
  workspace_timezone: string;
  today: string;
  can_publish_directly: boolean;
  can_edit_others: boolean;
  chips: Chip[];
  open_slots: OpenSlot[];
  events: CalendarEvent[];
  unscheduled_drafts: { id: string; title: string; caption: string; updated_at: string }[];
  filters: {
    channels: { id: string; name: string; platform: string; connected: boolean }[];
    statuses: string[];
    tags: string[];
    categories: { id: string; name: string }[];
  };
}

export interface SlotsData {
  days: { value: number; label: string }[];
  timezone: string;
  accounts: { id: string; name: string; platform: string; slots: { id: string; day_of_week: number; time: string; is_active: boolean }[] }[];
}

export interface QueueRow {
  id: string;
  name: string;
  is_active: boolean;
  account: { id: string; name: string; platform: string };
  category: { id: string; name: string } | null;
  entry_count: number;
}

export interface QueuesData {
  queues: QueueRow[];
  accounts: { id: string; name: string; platform: string }[];
  categories: { id: string; name: string }[];
}

export interface QueueDetail {
  queue: QueueRow;
  entries: { id: string; post_id: string; position: number; slot: string | null; title: string; caption: string; status: string; author: string | null }[];
}

export interface OrgChip {
  id: string;
  post_id: string;
  workspace_id: string;
  workspace_name: string;
  color: string;
  at: string | null;
  status: string;
  platform: string;
  account: { id: string; name: string };
  title: string;
  caption: string;
}

export interface OrgCalendar {
  today: string;
  workspaces: { id: string; name: string; color: string }[];
  selected: string[];
  accounts: { id: string; name: string; platform: string; workspace_id: string }[];
  tags: string[];
  statuses: string[];
  chips: OrgChip[];
}
