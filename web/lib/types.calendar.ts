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
  unscheduled_drafts: { id: string; title: string; caption: string; updated_at: string }[];
  filters: {
    channels: { id: string; name: string; platform: string; connected: boolean }[];
    statuses: string[];
    tags: string[];
    categories: { id: string; name: string }[];
  };
}
