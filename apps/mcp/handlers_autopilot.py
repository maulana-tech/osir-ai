"""MCP tools for the Osir AI autopilot agent.

These give an autonomous agent (see ``agent/``) hands on the parts of
Studio a human social-media manager touches every day but that the
original Agent API left out: the inbox, the idea board, the posting
schedule, the approval queue, and the humans themselves.

Every tool re-checks the same workspace permission the HTMX view for
that action requires, and every account-scoped read is filtered by the
API key's social-account allowlist, so a key scoped to one channel
never sees another channel's DMs.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, F
from django.db.models.functions import Coalesce

from apps.approvals.services import submit_for_review
from apps.calendar.models import PostingSlot
from apps.composer.models import Idea, PlatformPost
from apps.composer.services import _APPROVAL_MODES_BLOCKING_DIRECT_SCHEDULE
from apps.inbox import services as inbox_services
from apps.inbox.models import InboxMessage, InternalNote, SavedReply
from apps.mcp.handlers import (
    _get_post_for_key,
    _parse_iso_datetime,
    _parse_uuid,
    _require_perm,
    _serialize_post,
    _wrap_text,
)
from apps.mcp.protocol import INTERNAL_ERROR, INVALID_PARAMS, JsonRpcError
from apps.mcp.tools import Tool, register_tool
from apps.members.models import WorkspaceMembership
from apps.notifications.engine import notify
from apps.notifications.models import EventType

_LIMIT_DEFAULT = 50
_LIMIT_MAX = 100
_SCHEDULE_WINDOW_MAX = timedelta(days=31)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _limit(args: dict) -> int:
    raw = args.get("limit", _LIMIT_DEFAULT)
    if not isinstance(raw, int) or isinstance(raw, bool) or not 1 <= raw <= _LIMIT_MAX:
        raise JsonRpcError(INVALID_PARAMS, f"limit must be an integer between 1 and {_LIMIT_MAX}")
    return raw


def _allowed_account_ids(api_key) -> list:
    return [sa.id for sa in api_key.social_accounts.all()]


def _actor(context: dict[str, Any]):
    """The human the agent acts on behalf of: the key's issuer.

    Writes that need an author (replies, notes, approval submissions) are
    attributed to them, exactly as if they had clicked the button.
    """
    user = context["api_key"].issued_by
    if user is None:
        raise JsonRpcError(INVALID_PARAMS, "This API key has no issuing user; re-issue it to use this tool")
    return user


def _visible_messages_qs(api_key):
    return InboxMessage.objects.filter(
        workspace_id=api_key.workspace_id,
        social_account_id__in=_allowed_account_ids(api_key),
    ).select_related("social_account", "assigned_to", "parent_message", "related_post__post")


def _name(user) -> str | None:
    return user.display_name if user is not None else None


def _get_message_for_key(api_key, message_id_str: str) -> InboxMessage:
    message_id = _parse_uuid(message_id_str, "message_id")
    try:
        return _visible_messages_qs(api_key).get(id=message_id)
    except InboxMessage.DoesNotExist as exc:
        raise JsonRpcError(INVALID_PARAMS, "Message not found") from exc


def _serialize_message(m: InboxMessage, *, reply_count: int | None = None) -> dict:
    return {
        "id": str(m.id),
        "message_type": m.message_type,
        "status": m.status,
        "sentiment": m.sentiment,
        "sender_name": m.sender_name,
        "sender_handle": m.sender_handle,
        "body": m.body,
        "social_account_id": str(m.social_account_id),
        "platform": m.social_account.platform,
        "account_name": m.social_account.account_name,
        "related_post_id": str(m.related_post.post_id) if m.related_post is not None else None,
        "parent_message_id": str(m.parent_message_id) if m.parent_message_id else None,
        "assigned_to": _name(m.assigned_to),
        "received_at": m.received_at.isoformat(),
        "reply_count": reply_count if reply_count is not None else m.replies.count(),
    }


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


def _list_inbox_messages(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "use_inbox")
    api_key = context["api_key"]
    limit = _limit(args)

    qs = _visible_messages_qs(api_key).annotate(reply_count=Count("replies"))
    for field in ("status", "message_type", "sentiment"):
        if args.get(field):
            qs = qs.filter(**{field: args[field]})
    if args.get("since"):
        qs = qs.filter(received_at__gte=_parse_iso_datetime(args["since"], "since"))
    if args.get("unanswered_only"):
        qs = qs.filter(reply_count=0)

    rows = list(qs.order_by("-received_at", "id")[:limit])
    return _wrap_text(
        {
            "messages": [_serialize_message(m, reply_count=m.reply_count) for m in rows],
            "count": len(rows),
            "truncated": len(rows) == limit,
        }
    )


register_tool(
    Tool(
        name="list_inbox_messages",
        description=(
            "List inbox items (comments, mentions, DMs, reviews) on the accounts this key can act on, "
            "newest first. Filter by status (unread/open/resolved/archived), message_type, sentiment, "
            "`since` (ISO-8601), and `unanswered_only` to get only items nobody has replied to yet. "
            "Use get_inbox_message for the full thread before replying."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": list(InboxMessage.Status.values)},
                "message_type": {"type": "string", "enum": list(InboxMessage.MessageType.values)},
                "sentiment": {"type": "string", "enum": list(InboxMessage.Sentiment.values)},
                "since": {"type": "string", "description": "ISO-8601 lower bound on received_at."},
                "unanswered_only": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": _LIMIT_MAX, "default": _LIMIT_DEFAULT},
            },
            "additionalProperties": False,
        },
        handler=_list_inbox_messages,
    )
)


def _get_inbox_message(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "use_inbox")
    if "message_id" not in args:
        raise JsonRpcError(INVALID_PARAMS, "message_id is required")
    m = _get_message_for_key(context["api_key"], args["message_id"])
    payload = _serialize_message(m)
    parent = m.parent_message
    payload["parent"] = (
        {"id": str(parent.id), "sender_name": parent.sender_name, "body": parent.body} if parent is not None else None
    )
    payload["replies"] = [
        {
            "id": str(r.id),
            "author": _name(r.author),
            "body": r.body,
            "sent_at": r.sent_at.isoformat(),
            "delivered": bool(r.platform_reply_id),
        }
        for r in m.replies.select_related("author").order_by("sent_at")
    ]
    payload["internal_notes"] = [
        {
            "author": _name(n.author),
            "body": n.body,
            "created_at": n.created_at.isoformat(),
        }
        for n in m.internal_notes.select_related("author").order_by("created_at")
    ]
    related = m.related_post
    if related is not None:
        payload["related_post"] = {
            "id": str(related.post_id),
            "title": related.post.title,
            "caption": related.effective_caption,
        }
    return _wrap_text(payload)


register_tool(
    Tool(
        name="get_inbox_message",
        description=(
            "Full detail for one inbox item: the message, its parent (for threaded comments), every "
            "reply already sent (with whether the platform accepted it), team-only internal notes, "
            "and the post it was left on. Read this before deciding whether to reply or escalate."
        ),
        input_schema={
            "type": "object",
            "properties": {"message_id": {"type": "string", "format": "uuid"}},
            "required": ["message_id"],
            "additionalProperties": False,
        },
        handler=_get_inbox_message,
    )
)


def _list_saved_replies(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "use_inbox")
    rows = SavedReply.objects.for_workspace(context["api_key"].workspace_id).order_by("title")
    return _wrap_text({"saved_replies": [{"id": str(r.id), "title": r.title, "body": r.body} for r in rows]})


register_tool(
    Tool(
        name="list_saved_replies",
        description=(
            "The workspace's canned replies (title + body). Prefer these, adapted to the message, "
            "for routine questions so the agent's voice matches the team's."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_list_saved_replies,
    )
)


def _reply_to_inbox_message(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "reply_from_inbox")
    if "message_id" not in args:
        raise JsonRpcError(INVALID_PARAMS, "message_id is required")
    body = args.get("body")
    if not isinstance(body, str) or not body.strip():
        raise JsonRpcError(INVALID_PARAMS, "body must be a non-empty string")
    m = _get_message_for_key(context["api_key"], args["message_id"])
    try:
        reply = inbox_services.send_reply(m, body.strip(), author=_actor(context))
    except JsonRpcError:
        raise
    except Exception as exc:
        raise JsonRpcError(INTERNAL_ERROR, f"The platform rejected the reply: {exc}") from exc
    return _wrap_text(
        {
            "reply_id": str(reply.id),
            "delivered": bool(reply.platform_reply_id),
            "message_status": m.status,
        }
    )


register_tool(
    Tool(
        name="reply_to_inbox_message",
        description=(
            "Send a public reply (comment) or direct message back to the sender through the platform "
            "API and record it on the thread. `delivered` is false when the platform has no reply API "
            "for this item type (the reply is then kept as an internal record only). Irreversible: "
            "only call this when the reply is safe to send without human review."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "format": "uuid"},
                "body": {"type": "string", "maxLength": 5000},
            },
            "required": ["message_id", "body"],
            "additionalProperties": False,
        },
        handler=_reply_to_inbox_message,
    )
)


def _triage_inbox_message(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "use_inbox")
    if "message_id" not in args:
        raise JsonRpcError(INVALID_PARAMS, "message_id is required")
    m = _get_message_for_key(context["api_key"], args["message_id"])

    fields = []
    if args.get("status"):
        m.status = args["status"]
        fields.append("status")
    if args.get("sentiment"):
        m.sentiment = args["sentiment"]
        m.sentiment_source = InboxMessage.SentimentSource.MANUAL
        fields += ["sentiment", "sentiment_source"]
    note = args.get("internal_note")
    if note:
        _require_perm(context, "reply_from_inbox")
        InternalNote.objects.create(inbox_message=m, author=_actor(context), body=note.strip())
    if not fields and not note:
        raise JsonRpcError(INVALID_PARAMS, "Provide at least one of status, sentiment, internal_note")
    if fields:
        m.save(update_fields=fields)
    return _wrap_text(_serialize_message(m))


register_tool(
    Tool(
        name="triage_inbox_message",
        description=(
            "Update an inbox item without replying to the sender: set status (e.g. resolved for spam "
            "or thanks-only comments, open to leave it for a human), correct the sentiment, and/or "
            "attach a team-only internal note explaining what the agent saw and why it escalated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "format": "uuid"},
                "status": {"type": "string", "enum": list(InboxMessage.Status.values)},
                "sentiment": {"type": "string", "enum": list(InboxMessage.Sentiment.values)},
                "internal_note": {"type": "string", "maxLength": 5000},
            },
            "required": ["message_id"],
            "additionalProperties": False,
        },
        handler=_triage_inbox_message,
    )
)


# ---------------------------------------------------------------------------
# Ideas
# ---------------------------------------------------------------------------


def _list_ideas(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "create_posts")
    limit = _limit(args)
    qs = Idea.objects.for_workspace(context["api_key"].workspace_id).select_related("group")
    if args.get("status"):
        qs = qs.filter(status=args["status"])
    if args.get("unused_only", True):
        qs = qs.filter(post__isnull=True)
    rows = list(qs.order_by("position", "-created_at")[:limit])
    return _wrap_text(
        {
            "ideas": [
                {
                    "id": str(i.id),
                    "title": i.title,
                    "description": i.description,
                    "tags": i.tags if isinstance(i.tags, list) else [],
                    "status": i.status,
                    "group": i.group.name if i.group_id else None,
                    "media_asset_id": str(i.media_asset_id) if i.media_asset_id else None,
                    "post_id": str(i.post_id) if i.post_id else None,
                    "created_at": i.created_at.isoformat(),
                }
                for i in rows
            ],
            "count": len(rows),
        }
    )


register_tool(
    Tool(
        name="list_ideas",
        description=(
            "The workspace's idea board (Kanban cards a human jotted down for future posts). By default "
            "only ideas not yet turned into a post are returned. Pass an idea's id as `idea_id` to "
            "create_draft to turn it into a draft and link the two."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": list(Idea.Status.values)},
                "unused_only": {"type": "boolean", "default": True},
                "limit": {"type": "integer", "minimum": 1, "maximum": _LIMIT_MAX, "default": _LIMIT_DEFAULT},
            },
            "additionalProperties": False,
        },
        handler=_list_ideas,
    )
)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def _get_schedule(args: dict, context: dict[str, Any]) -> dict:
    api_key = context["api_key"]
    for key in ("start", "end"):
        if key not in args:
            raise JsonRpcError(INVALID_PARAMS, f"{key} is required (ISO 8601)")
    start = _parse_iso_datetime(args["start"], "start")
    end = _parse_iso_datetime(args["end"], "end")
    if end <= start:
        raise JsonRpcError(INVALID_PARAMS, "end must be after start")
    if end - start > _SCHEDULE_WINDOW_MAX:
        raise JsonRpcError(INVALID_PARAMS, f"window may not exceed {_SCHEDULE_WINDOW_MAX.days} days")

    allowed = _allowed_account_ids(api_key)
    slots = PostingSlot.objects.filter(social_account_id__in=allowed, is_active=True).select_related("social_account")
    posts = (
        PlatformPost.objects.filter(social_account_id__in=allowed)
        .annotate(effective_at=Coalesce(F("scheduled_at"), F("post__scheduled_at")))
        .filter(effective_at__gte=start, effective_at__lt=end)
        .exclude(status__in=[PlatformPost.Status.REJECTED, PlatformPost.Status.FAILED])
        .select_related("post", "social_account")
        .order_by("effective_at")
    )
    return _wrap_text(
        {
            "timezone": api_key.workspace.timezone or "UTC",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "posting_slots": [
                {
                    "social_account_id": str(s.social_account_id),
                    "platform": s.social_account.platform,
                    "account_name": s.social_account.account_name,
                    "day_of_week": s.day_of_week,
                    "day_label": s.get_day_of_week_display(),
                    "time": s.time.strftime("%H:%M"),
                }
                for s in slots.order_by("day_of_week", "time")
            ],
            "posts": [
                {
                    "post_id": str(pp.post_id),
                    "social_account_id": str(pp.social_account_id),
                    "platform": pp.social_account.platform,
                    "status": pp.status,
                    "scheduled_at": pp.effective_at.isoformat(),
                    "title": pp.post.title,
                    "caption_snippet": pp.post.caption[:140],
                }
                for pp in posts
            ],
        }
    )


register_tool(
    Tool(
        name="get_schedule",
        description=(
            "What is already planned in a date window (max 31 days) for this key's accounts: the "
            "recurring posting slots the team defined (weekday + local time per account) and every "
            "post with a scheduled time in the window, with its status. Compare the two to find "
            "empty slots worth filling with a draft."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "ISO-8601 window start (inclusive)."},
                "end": {"type": "string", "description": "ISO-8601 window end (exclusive)."},
            },
            "required": ["start", "end"],
            "additionalProperties": False,
        },
        handler=_get_schedule,
    )
)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


def _submit_for_approval(args: dict, context: dict[str, Any]) -> dict:
    _require_perm(context, "create_posts")
    if "post_id" not in args:
        raise JsonRpcError(INVALID_PARAMS, "post_id is required")
    api_key = context["api_key"]
    post = _get_post_for_key(api_key, args["post_id"])
    result = submit_for_review(post, _actor(context), api_key.workspace)
    if isinstance(result, list):
        raise JsonRpcError(INVALID_PARAMS, "No draft platform posts to submit (already submitted or scheduled?)")
    post.refresh_from_db()
    return _wrap_text(_serialize_post(post, context))


register_tool(
    Tool(
        name="submit_for_approval",
        description=(
            "Hand a draft to the humans: moves every draft target of the post to pending_review and "
            "notifies every workspace member who can approve. This is how the agent surfaces content "
            "decisions instead of publishing on its own. Only drafts (or posts sent back with changes "
            "requested / rejected) can be submitted."
        ),
        input_schema={
            "type": "object",
            "properties": {"post_id": {"type": "string", "format": "uuid"}},
            "required": ["post_id"],
            "additionalProperties": False,
        },
        handler=_submit_for_approval,
    )
)


# ---------------------------------------------------------------------------
# Humans
# ---------------------------------------------------------------------------

_DECIDER_PERMS = ("approve_posts", "manage_workspace_settings")


def _deciders(api_key):
    """People who should hear from the agent: the key's issuer plus anyone who can approve or run the workspace."""
    users = {}
    if api_key.issued_by_id and api_key.issued_by.is_active:
        users[api_key.issued_by_id] = api_key.issued_by
    memberships = WorkspaceMembership.objects.filter(workspace_id=api_key.workspace_id).select_related(
        "user", "custom_role"
    )
    for membership in memberships:
        perms = membership.effective_permissions
        if any(perms.get(p, False) for p in _DECIDER_PERMS):
            users.setdefault(membership.user_id, membership.user)
    return list(users.values())


def _notify_team(args: dict, context: dict[str, Any]) -> dict:
    api_key = context["api_key"]
    title = args.get("title")
    body = args.get("body", "")
    if not isinstance(title, str) or not title.strip():
        raise JsonRpcError(INVALID_PARAMS, "title must be a non-empty string")
    kind = args.get("kind", "decision")
    event_type = EventType.AGENT_DIGEST if kind == "digest" else EventType.AGENT_DECISION_NEEDED

    data: dict[str, Any] = {"workspace_id": str(api_key.workspace_id), "source": "osir-agent", "kind": kind}
    if args.get("post_id"):
        data["post_id"] = str(_get_post_for_key(api_key, args["post_id"]).id)
    if args.get("message_id"):
        data["message_id"] = str(_get_message_for_key(api_key, args["message_id"]).id)

    recipients = _deciders(api_key)
    sent = [
        u.display_name
        for u in recipients
        if notify(user=u, event_type=event_type, title=title.strip(), body=body, data=data) is not None
    ]
    return _wrap_text({"notified": len(sent), "recipients": sent, "event_type": event_type})


register_tool(
    Tool(
        name="notify_team",
        description=(
            "Ping the humans. `kind=decision` (default) is for something only a person should decide: a "
            "negative or sensitive inbox message, a refund/complaint, an ambiguous request, a risky "
            "reply. `kind=digest` is for the periodic summary of what the agent did and what it saw; "
            "digests respect quiet hours, decisions do not. Attach post_id or message_id so the "
            "notification deep-links to the thing. Recipients: the key's issuer plus every member who "
            "can approve posts or manage the workspace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 200},
                "body": {"type": "string", "maxLength": 4000, "default": ""},
                "kind": {"type": "string", "enum": ["decision", "digest"], "default": "decision"},
                "post_id": {"type": "string", "format": "uuid"},
                "message_id": {"type": "string", "format": "uuid"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=_notify_team,
    )
)


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def _get_workspace_policy(args: dict, context: dict[str, Any]) -> dict:
    """What the agent may do here. Read at the start of every run.

    ``agent_autonomy`` is the human's dial in Workspace Settings → Approvals;
    ``can_publish`` reflects the key's own permissions, which remain the hard
    gate regardless of the dial.
    """
    workspace = context["workspace"]
    perms = context["membership"].effective_permissions
    mode = workspace.approval_workflow_mode
    return _wrap_text(
        {
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "timezone": workspace.timezone or "UTC",
            "agent_autonomy": workspace.agent_autonomy,
            "approval_workflow_mode": mode,
            "direct_scheduling_allowed": mode not in _APPROVAL_MODES_BLOCKING_DIRECT_SCHEDULE,
            "can_publish": bool(perms.get("publish_directly")),
            "permissions": sorted(k for k, v in perms.items() if v),
            "default_hashtags": workspace.default_hashtags or [],
            "default_first_comment": workspace.default_first_comment,
        }
    )


register_tool(
    Tool(
        name="get_workspace_policy",
        description=(
            "Read this first. Returns the workspace's autonomy level for the agent (off | draft_only | "
            "autopilot), whether the approval workflow permits direct scheduling, whether this key may "
            "publish, the key's permissions, the workspace timezone, and default hashtags/first comment. "
            "Scheduling directly is only appropriate when agent_autonomy is autopilot AND "
            "direct_scheduling_allowed AND can_publish are all true; otherwise create drafts and submit them."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_get_workspace_policy,
    )
)
