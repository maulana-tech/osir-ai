"""Social inbox for the web UI: feed, thread, replies, triage, saved replies, SLA."""

from __future__ import annotations

import logging
import uuid

from django.db.models import Count, Q
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.inbox import services
from apps.inbox.models import InboxMessage, InboxSLAConfig, InternalNote, SavedReply
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.webapi.common import require_perm, scoped

logger = logging.getLogger(__name__)
router = Router(tags=["inbox"])

PAGE = 50


def _member(m: WorkspaceMembership) -> dict:
    return {"id": str(m.user_id), "name": m.user.display_name, "email": m.user.email}


def _account(sa: SocialAccount) -> dict:
    return {"id": str(sa.id), "platform": sa.platform, "name": sa.account_name, "avatar_url": sa.avatar_url}


def _message(m: InboxMessage) -> dict:
    return {
        "id": str(m.id),
        "message_type": m.message_type,
        "status": m.status,
        "sentiment": m.sentiment,
        "sentiment_source": m.sentiment_source,
        "sender_name": m.sender_name,
        "sender_handle": m.sender_handle,
        "sender_avatar_url": m.sender_avatar_url,
        "body": m.body,
        "account": _account(m.social_account),
        "assigned_to": {"id": str(m.assigned_to.pk), "name": m.assigned_to.display_name} if m.assigned_to else None,
        "related_post_id": str(m.related_post.post_id) if m.related_post is not None else None,
        "parent_message_id": str(m.parent_message_id) if m.parent_message_id else None,
        "received_at": m.received_at.isoformat(),
        "reply_count": getattr(m, "reply_count", 0),
        "note_count": getattr(m, "note_count", 0),
    }


def _get_message(workspace_id, message_id) -> InboxMessage:
    try:
        return InboxMessage.objects.select_related("social_account", "assigned_to", "related_post").get(
            id=message_id, workspace_id=workspace_id
        )
    except InboxMessage.DoesNotExist as exc:
        raise HttpError(404, "Message not found") from exc


def _sla(workspace_id) -> dict | None:
    cfg = InboxSLAConfig.objects.filter(workspace_id=workspace_id).first()
    if cfg is None:
        return None
    return {
        "is_active": cfg.is_active,
        "target_response_minutes": cfg.target_response_minutes,
        "auto_resolve_on_reply": cfg.auto_resolve_on_reply,
    }


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/inbox", summary="Inbox feed with filters")
def feed(
    request,
    workspace_id: uuid.UUID,
    view: str = "all",
    q: str = "",
    assigned: str = "",
    date_from: str = "",
    date_to: str = "",
    offset: int = 0,
    limit: int = PAGE,
):
    membership = scoped(request, workspace_id)
    require_perm(membership, "use_inbox")
    qs = (
        InboxMessage.objects.for_workspace(workspace_id)
        .select_related("social_account", "assigned_to", "related_post")
        .annotate(reply_count=Count("replies", distinct=True), note_count=Count("internal_notes", distinct=True))
    )
    if view == "mine":
        qs = qs.filter(assigned_to_id=request.user.pk)
    elif view == "unassigned":
        qs = qs.filter(assigned_to__isnull=True)
    for param, field in (
        ("platform", "social_account__platform__in"),
        ("account", "social_account_id__in"),
        ("type", "message_type__in"),
        ("status", "status__in"),
        ("sentiment", "sentiment__in"),
    ):
        values = [v for v in request.GET.getlist(param) if v]
        if values:
            qs = qs.filter(**{field: values})
    if assigned == "unassigned":
        qs = qs.filter(assigned_to__isnull=True)
    elif assigned:
        qs = qs.filter(assigned_to_id=assigned)
    if date_from:
        qs = qs.filter(received_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(received_at__date__lte=date_to)
    if q.strip():
        term = q.strip()
        qs = qs.filter(Q(body__icontains=term) | Q(sender_name__icontains=term) | Q(sender_handle__icontains=term))

    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    rows = list(qs.order_by("-received_at")[offset : offset + limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]

    return {
        "messages": [_message(m) for m in rows],
        "next_offset": offset + limit if has_more else None,
        "unread_count": InboxMessage.objects.for_workspace(workspace_id)
        .filter(status=InboxMessage.Status.UNREAD)
        .count(),
        "accounts": [
            _account(a)
            for a in SocialAccount.objects.for_workspace(workspace_id)
            .filter(connection_status=SocialAccount.ConnectionStatus.CONNECTED)
            .order_by("platform", "account_name")
        ],
        "team": [
            _member(m) for m in WorkspaceMembership.objects.filter(workspace_id=workspace_id).select_related("user")
        ],
        "sla": _sla(workspace_id),
        "can_reply": bool(membership.effective_permissions.get("reply_from_inbox")),
        "can_manage": bool(membership.effective_permissions.get("manage_workspace_settings")),
    }


# ---------------------------------------------------------------------------
# Thread
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/inbox/{uuid:message_id}", summary="One message with its thread")
def detail(request, workspace_id: uuid.UUID, message_id: uuid.UUID):
    membership = scoped(request, workspace_id)
    require_perm(membership, "use_inbox")
    m = _get_message(workspace_id, message_id)
    if m.status == InboxMessage.Status.UNREAD:
        m.status = InboxMessage.Status.OPEN
        m.save(update_fields=["status"])

    thread = [
        {
            "kind": "reply",
            "id": str(r.id),
            "author": r.author.display_name if r.author else None,
            "body": r.body,
            "at": r.sent_at.isoformat(),
            "delivered": bool(r.platform_reply_id),
        }
        for r in m.replies.select_related("author")
    ] + [
        {
            "kind": "note",
            "id": str(n.id),
            "author": n.author.display_name if n.author else None,
            "body": n.body,
            "at": n.created_at.isoformat(),
        }
        for n in m.internal_notes.select_related("author")
    ]
    thread.sort(key=lambda x: x["at"])
    children = InboxMessage.objects.filter(parent_message=m).select_related(
        "social_account", "assigned_to", "related_post"
    )
    payload = _message(m)
    payload.update(
        {
            "thread": thread,
            "parent": _message(m.parent_message) if m.parent_message else None,
            "children": [_message(c) for c in children],
            "related_post": (
                {"id": str(m.related_post.post_id), "caption": m.related_post.effective_caption[:200]}
                if m.related_post is not None
                else None
            ),
            "saved_replies": [
                {"id": str(r.id), "title": r.title, "body": r.body}
                for r in SavedReply.objects.for_workspace(workspace_id).order_by("title")
            ],
        }
    )
    return payload


class Body(Schema):
    body: str


@router.post("/{workspace_id}/inbox/{uuid:message_id}/reply", summary="Reply through the platform")
def reply(request, workspace_id: uuid.UUID, message_id: uuid.UUID, payload: Body):
    membership = scoped(request, workspace_id)
    require_perm(membership, "reply_from_inbox")
    m = _get_message(workspace_id, message_id)
    body = payload.body.strip()
    if not body:
        raise HttpError(400, "Reply cannot be empty")
    try:
        r = services.send_reply(m, body, author=request.user)
    except Exception as exc:
        logger.exception("Failed to send reply for message %s", m.id)
        raise HttpError(502, f"Could not send the reply: {services.reply_failure_reason(exc)}") from exc
    return {"id": str(r.id), "delivered": bool(r.platform_reply_id), "status": m.status}


@router.post("/{workspace_id}/inbox/{uuid:message_id}/note", summary="Add a team-only note")
def note(request, workspace_id: uuid.UUID, message_id: uuid.UUID, payload: Body):
    membership = scoped(request, workspace_id)
    require_perm(membership, "reply_from_inbox")
    m = _get_message(workspace_id, message_id)
    body = payload.body.strip()
    if not body:
        raise HttpError(400, "Note cannot be empty")
    n = InternalNote.objects.create(inbox_message=m, author=request.user, body=body)
    return {"id": str(n.id), "at": n.created_at.isoformat()}


class Assign(Schema):
    user_id: uuid.UUID | None = None


@router.post("/{workspace_id}/inbox/{uuid:message_id}/assign", summary="Assign to a teammate (null to unassign)")
def assign(request, workspace_id: uuid.UUID, message_id: uuid.UUID, payload: Assign):
    membership = scoped(request, workspace_id)
    require_perm(membership, "reply_from_inbox")
    m = _get_message(workspace_id, message_id)
    try:
        services.assign_message(m, payload.user_id, actor=request.user)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return _message(m)


class Triage(Schema):
    status: str | None = None
    sentiment: str | None = None


@router.post("/{workspace_id}/inbox/{uuid:message_id}/triage", summary="Set status and/or sentiment")
def triage(request, workspace_id: uuid.UUID, message_id: uuid.UUID, payload: Triage):
    membership = scoped(request, workspace_id)
    require_perm(membership, "reply_from_inbox")
    m = _get_message(workspace_id, message_id)
    fields = []
    if payload.status:
        if payload.status not in InboxMessage.Status.values:
            raise HttpError(400, "Invalid status")
        m.status = payload.status
        fields.append("status")
    if payload.sentiment:
        if payload.sentiment not in InboxMessage.Sentiment.values:
            raise HttpError(400, "Invalid sentiment")
        m.sentiment = payload.sentiment
        m.sentiment_source = InboxMessage.SentimentSource.MANUAL
        fields += ["sentiment", "sentiment_source"]
    if not fields:
        raise HttpError(400, "Nothing to change")
    m.save(update_fields=fields)
    return _message(m)


class Bulk(Schema):
    message_ids: list[uuid.UUID]
    action: str
    value: str = ""


@router.post("/{workspace_id}/inbox/bulk", summary="Bulk mark read / resolve / archive / assign")
def bulk(request, workspace_id: uuid.UUID, payload: Bulk):
    membership = scoped(request, workspace_id)
    require_perm(membership, "reply_from_inbox")
    if payload.action not in services.BULK_ACTIONS:
        raise HttpError(400, "Unknown action")
    touched = services.bulk_action(workspace_id, payload.message_ids, payload.action, payload.value)
    return {"touched": touched}


# ---------------------------------------------------------------------------
# Saved replies and SLA
# ---------------------------------------------------------------------------


class SavedReplyIn(Schema):
    title: str
    body: str


def _saved(r: SavedReply) -> dict:
    return {"id": str(r.id), "title": r.title, "body": r.body, "updated_at": r.updated_at.isoformat()}


@router.get("/{workspace_id}/inbox/saved-replies", summary="Saved replies")
def saved_replies(request, workspace_id: uuid.UUID):
    membership = scoped(request, workspace_id)
    require_perm(membership, "use_inbox")
    return {"saved_replies": [_saved(r) for r in SavedReply.objects.for_workspace(workspace_id).order_by("title")]}


@router.post("/{workspace_id}/inbox/saved-replies", summary="Create a saved reply")
def saved_reply_create(request, workspace_id: uuid.UUID, payload: SavedReplyIn):
    membership = scoped(request, workspace_id)
    require_perm(membership, "manage_workspace_settings")
    if not payload.title.strip() or not payload.body.strip():
        raise HttpError(400, "Title and body are required")
    r = SavedReply.objects.create(
        workspace_id=workspace_id, title=payload.title.strip(), body=payload.body.strip(), created_by=request.user
    )
    return _saved(r)


@router.put("/{workspace_id}/inbox/saved-replies/{uuid:reply_id}", summary="Edit a saved reply")
def saved_reply_update(request, workspace_id: uuid.UUID, reply_id: uuid.UUID, payload: SavedReplyIn):
    membership = scoped(request, workspace_id)
    require_perm(membership, "manage_workspace_settings")
    try:
        r = SavedReply.objects.get(id=reply_id, workspace_id=workspace_id)
    except SavedReply.DoesNotExist as exc:
        raise HttpError(404, "Saved reply not found") from exc
    r.title, r.body = payload.title.strip(), payload.body.strip()
    r.save(update_fields=["title", "body", "updated_at"])
    return _saved(r)


@router.delete("/{workspace_id}/inbox/saved-replies/{uuid:reply_id}", summary="Delete a saved reply")
def saved_reply_delete(request, workspace_id: uuid.UUID, reply_id: uuid.UUID):
    membership = scoped(request, workspace_id)
    require_perm(membership, "manage_workspace_settings")
    deleted, _ = SavedReply.objects.filter(id=reply_id, workspace_id=workspace_id).delete()
    if not deleted:
        raise HttpError(404, "Saved reply not found")
    return {"deleted": True}


class SlaIn(Schema):
    is_active: bool
    target_response_minutes: int
    auto_resolve_on_reply: bool


@router.get("/{workspace_id}/inbox/sla", summary="SLA settings")
def sla_get(request, workspace_id: uuid.UUID):
    membership = scoped(request, workspace_id)
    require_perm(membership, "use_inbox")
    return _sla(workspace_id) or {"is_active": False, "target_response_minutes": 120, "auto_resolve_on_reply": False}


@router.put("/{workspace_id}/inbox/sla", summary="Update SLA settings")
def sla_put(request, workspace_id: uuid.UUID, payload: SlaIn):
    membership = scoped(request, workspace_id)
    require_perm(membership, "manage_workspace_settings")
    if payload.target_response_minutes < 1:
        raise HttpError(400, "target_response_minutes must be positive")
    cfg, _ = InboxSLAConfig.objects.get_or_create(
        workspace_id=workspace_id, defaults={"target_response_minutes": 120, "is_active": False}
    )
    cfg.is_active = payload.is_active
    cfg.target_response_minutes = payload.target_response_minutes
    cfg.auto_resolve_on_reply = payload.auto_resolve_on_reply
    cfg.save()
    return _sla(workspace_id)
