export interface InboxAccount {
  id: string;
  platform: string;
  name: string;
  avatar_url: string;
}

export interface Member {
  id: string;
  name: string;
  email: string;
}

export interface InboxMessage {
  id: string;
  message_type: "comment" | "mention" | "dm" | "review";
  status: "unread" | "open" | "resolved" | "archived";
  sentiment: "positive" | "neutral" | "negative" | "";
  sentiment_source: string;
  sender_name: string;
  sender_handle: string;
  sender_avatar_url: string;
  body: string;
  account: InboxAccount;
  assigned_to: { id: string; name: string } | null;
  related_post_id: string | null;
  parent_message_id: string | null;
  received_at: string;
  reply_count: number;
  note_count: number;
}

export interface ThreadItem {
  kind: "reply" | "note";
  id: string;
  author: string | null;
  body: string;
  at: string;
  delivered?: boolean;
}

export interface InboxDetail extends InboxMessage {
  thread: ThreadItem[];
  parent: InboxMessage | null;
  children: InboxMessage[];
  related_post: { id: string; caption: string } | null;
  saved_replies: { id: string; title: string; body: string }[];
}

export interface Sla {
  is_active: boolean;
  target_response_minutes: number;
  auto_resolve_on_reply: boolean;
}

export interface InboxFeed {
  messages: InboxMessage[];
  next_offset: number | null;
  unread_count: number;
  accounts: InboxAccount[];
  team: Member[];
  sla: Sla | null;
  can_reply: boolean;
  can_manage: boolean;
}
