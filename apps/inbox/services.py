"""Inbox service layer shared by the HTMX views and the MCP tools.

The reply path lives here so the agent surface (``apps.mcp``) and the
web UI cannot drift: same provider dispatch, same "only record what the
platform accepted" rule, same auto-resolve behaviour.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from providers import get_provider

from .models import InboxMessage, InboxReply, InboxSLAConfig

logger = logging.getLogger(__name__)

COMMENT_LIKE_TYPES = {
    InboxMessage.MessageType.COMMENT,
    InboxMessage.MessageType.MENTION,
    InboxMessage.MessageType.REVIEW,
}

# Meta's messaging window: after 24h a reply must be tagged as a human agent.
HUMAN_AGENT_AFTER = timedelta(hours=24)


def send_platform_reply(message: InboxMessage, body: str) -> str:
    """Post ``body`` back to the platform and return the platform's reply ID.

    Raises if the platform refuses it, so the caller can avoid recording a
    reply that was never delivered. ``NotImplementedError`` means the
    provider has no reply API for this item type.
    """
    from apps.publisher.engine import _resolve_publish_credentials

    account = message.social_account
    provider = get_provider(account.platform, _resolve_publish_credentials(account))

    # The messaging endpoints address a person, not a message, so carry the
    # sender's platform-scoped ID alongside the original payload.
    extra = dict(message.extra or {})
    if message.sender_handle:
        extra.setdefault("recipient_id", message.sender_handle)

    if message.message_type in COMMENT_LIKE_TYPES:
        result = provider.reply_to_comment(
            access_token=account.oauth_access_token,
            comment_id=message.platform_message_id,
            text=body,
            extra=extra,
        )
    else:
        overdue = timezone.now() - message.received_at > HUMAN_AGENT_AFTER
        result = provider.reply_to_message(
            access_token=account.oauth_access_token,
            message_id=message.platform_message_id,
            text=body,
            extra=extra,
            human_agent=overdue,
        )

    return result.platform_message_id


def send_reply(message: InboxMessage, body: str, author) -> InboxReply:
    """Deliver ``body`` via the platform, record it, and advance the message status.

    A reply is only recorded once the platform accepted it (or the platform
    has no reply API, in which case it is kept as a local record with an
    empty ``platform_reply_id``). Any other provider failure propagates so
    the caller can report it and keep the draft text.
    """
    try:
        platform_reply_id = send_platform_reply(message, body)
    except NotImplementedError:
        logger.info("Provider %s cannot send replies; recording locally.", message.social_account.platform)
        platform_reply_id = ""

    reply = InboxReply.objects.create(
        inbox_message=message,
        author=author,
        body=body,
        platform_reply_id=platform_reply_id,
    )

    sla_config = InboxSLAConfig.objects.filter(workspace=message.workspace, is_active=True).first()
    if sla_config and sla_config.auto_resolve_on_reply:
        message.status = InboxMessage.Status.RESOLVED
        message.save(update_fields=["status"])
    elif message.status == InboxMessage.Status.UNREAD:
        message.status = InboxMessage.Status.OPEN
        message.save(update_fields=["status"])

    return reply


def reply_failure_reason(exc: Exception) -> str:
    """A short, actionable reason for the user.

    The platform's own error text carries internal diagnostics (trace IDs, raw
    API JSON) that mean nothing to a workspace member, so it stays in the log
    and the UI gets a stable sentence instead.
    """
    from providers.exceptions import OAuthError, RateLimitError, TokenExpiredError

    if isinstance(exc, RateLimitError):
        return "the account has hit its rate limit. Wait a few minutes and try again."
    if isinstance(exc, TokenExpiredError | OAuthError):
        return "the connection has expired. Reconnect the account in Workspace Settings."
    return "the platform rejected it. Try again, or reconnect the account if this keeps happening."


def assign_message(message: InboxMessage, assignee_id, *, actor) -> InboxMessage:
    """Assign (or unassign with ``None``) and notify the assignee. Raises ValueError for non-members."""
    from apps.members.models import WorkspaceMembership
    from apps.notifications.engine import notify
    from apps.notifications.models import EventType

    if assignee_id:
        membership = (
            WorkspaceMembership.objects.filter(workspace_id=message.workspace_id, user_id=assignee_id)
            .select_related("user")
            .first()
        )
        if not membership:
            raise ValueError("User is not a workspace member.")
        message.assigned_to = membership.user
    else:
        message.assigned_to = None
    message.save(update_fields=["assigned_to"])

    if message.assigned_to and message.assigned_to != actor:
        notify(
            user=message.assigned_to,
            event_type=EventType.NEW_INBOX_MESSAGE,
            title=f"You were assigned a {message.get_message_type_display()}",
            body=f"From {message.sender_name}: {message.body[:100]}",
            data={"message_id": str(message.id), "workspace_id": str(message.workspace_id)},
        )
    return message


BULK_ACTIONS = ("mark_read", "resolve", "archive", "assign")


def bulk_action(workspace_id, message_ids, action: str, value: str = "") -> int:
    """Apply one bulk action to the given messages of a workspace; returns rows touched."""
    from apps.members.models import WorkspaceMembership

    qs = InboxMessage.objects.filter(id__in=message_ids, workspace_id=workspace_id)
    if action == "mark_read":
        return qs.filter(status=InboxMessage.Status.UNREAD).update(status=InboxMessage.Status.OPEN)
    if action == "resolve":
        return qs.exclude(status=InboxMessage.Status.ARCHIVED).update(status=InboxMessage.Status.RESOLVED)
    if action == "archive":
        return qs.update(status=InboxMessage.Status.ARCHIVED)
    if action == "assign" and value:
        membership = WorkspaceMembership.objects.filter(workspace_id=workspace_id, user_id=value).first()
        if membership:
            return qs.update(assigned_to=membership.user)
        return 0
    raise ValueError(f"Unknown bulk action: {action}")
