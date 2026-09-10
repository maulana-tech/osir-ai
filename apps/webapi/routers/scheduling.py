"""Calendar extras: custom events, bulk actions, posting slots and queues; the org-wide calendar."""

from __future__ import annotations

import datetime as dt
import uuid

from django.db.models import F
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.calendar import services
from apps.calendar.models import CustomCalendarEvent, PostingSlot, Queue, QueueEntry
from apps.common.validators import is_valid_hex_color
from apps.composer.models import ContentCategory, PlatformPost, Tag
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.webapi.common import require_perm, scoped
from apps.workspaces.models import Workspace

router = Router(tags=["scheduling"])
org_router = Router(tags=["scheduling"])


# ---------------------------------------------------------------------------
# Custom calendar events
# ---------------------------------------------------------------------------


def event_dict(e: CustomCalendarEvent) -> dict:
    return {
        "id": str(e.id),
        "title": e.title,
        "description": e.description,
        "start_date": e.start_date.isoformat(),
        "end_date": e.end_date.isoformat(),
        "color": e.color,
    }


class EventIn(Schema):
    title: str
    start_date: dt.date
    end_date: dt.date | None = None
    color: str = "#0a0a0a"
    description: str = ""


def _check_event(p: EventIn) -> None:
    if not p.title.strip():
        raise HttpError(400, "Title is required.")
    if not is_valid_hex_color(p.color):
        raise HttpError(400, "Color must be a 6-digit hex value like #3B82F6.")


@router.post("/{workspace_id}/calendar/events", summary="Add a calendar event")
def event_create(request, workspace_id: uuid.UUID, payload: EventIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    _check_event(payload)
    end = payload.end_date or payload.start_date
    e = CustomCalendarEvent.objects.create(
        workspace=m.workspace,
        title=payload.title.strip(),
        description=payload.description.strip(),
        start_date=payload.start_date,
        end_date=max(end, payload.start_date),
        color=payload.color,
        created_by=request.user,
    )
    return event_dict(e)


@router.put("/{workspace_id}/calendar/events/{uuid:event_id}", summary="Edit a calendar event")
def event_edit(request, workspace_id: uuid.UUID, event_id: uuid.UUID, payload: EventIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    _check_event(payload)
    e = get_object_or_404(CustomCalendarEvent, id=event_id, workspace=m.workspace)
    e.title, e.description, e.color = payload.title.strip(), payload.description.strip(), payload.color
    e.start_date = payload.start_date
    e.end_date = max(payload.end_date or payload.start_date, payload.start_date)
    e.save()
    return event_dict(e)


@router.delete("/{workspace_id}/calendar/events/{uuid:event_id}", summary="Delete a calendar event")
def event_delete(request, workspace_id: uuid.UUID, event_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    get_object_or_404(CustomCalendarEvent, id=event_id, workspace=m.workspace).delete()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------


class BulkIn(Schema):
    action: str
    platform_post_ids: list[uuid.UUID]


@router.post("/{workspace_id}/calendar/bulk", summary="Draft / delete / publish the selected rows")
def bulk(request, workspace_id: uuid.UUID, payload: BulkIn):
    m = scoped(request, workspace_id)
    try:
        count = services.bulk_platform_action(
            m.workspace, request.user, m.effective_permissions, payload.action, payload.platform_post_ids
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    except PermissionError as exc:
        raise HttpError(403, str(exc)) from exc
    return {"action": payload.action, "count": count}


# ---------------------------------------------------------------------------
# Posting slots
# ---------------------------------------------------------------------------


def _slot(s: PostingSlot) -> dict:
    return {"id": str(s.id), "day_of_week": s.day_of_week, "time": s.time.strftime("%H:%M"), "is_active": s.is_active}


def _slots_payload(workspace) -> dict:
    accounts = list(
        SocialAccount.objects.for_workspace(workspace.id)
        .filter(connection_status=SocialAccount.ConnectionStatus.CONNECTED)
        .prefetch_related("posting_slots")
        .order_by("platform", "account_name")
    )
    return {
        "days": [{"value": v, "label": label} for v, label in PostingSlot.DayOfWeek.choices],
        "timezone": workspace.effective_timezone or "UTC",
        "accounts": [
            {
                "id": str(a.id),
                "name": a.account_name,
                "platform": a.platform,
                "slots": [_slot(s) for s in sorted(a.posting_slots.all(), key=lambda s: (s.day_of_week, s.time))],
            }
            for a in accounts
        ],
    }


@router.get("/{workspace_id}/calendar/slots", summary="Posting slots per connected account")
def slots(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    return _slots_payload(m.workspace)


class SlotIn(Schema):
    social_account_id: uuid.UUID
    day_of_week: int
    time: str


def _time(value: str) -> dt.time:
    try:
        return dt.time.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise HttpError(400, "Invalid time format.") from exc


@router.post("/{workspace_id}/calendar/slots", summary="Add a posting slot")
def slot_create(request, workspace_id: uuid.UUID, payload: SlotIn):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_social_accounts")
    if payload.day_of_week not in PostingSlot.DayOfWeek.values:
        raise HttpError(400, "Invalid day_of_week.")
    account = get_object_or_404(SocialAccount, id=payload.social_account_id, workspace=m.workspace)
    slot, _ = PostingSlot.objects.get_or_create(
        social_account=account, day_of_week=payload.day_of_week, time=_time(payload.time), defaults={"is_active": True}
    )
    return _slot(slot)


class SlotTime(Schema):
    time: str


@router.patch("/{workspace_id}/calendar/slots/{uuid:slot_id}", summary="Change a slot's time")
def slot_update(request, workspace_id: uuid.UUID, slot_id: uuid.UUID, payload: SlotTime):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_social_accounts")
    slot = get_object_or_404(PostingSlot, id=slot_id, social_account__workspace=m.workspace)
    new_time = _time(payload.time)
    if (
        PostingSlot.objects.filter(social_account=slot.social_account, day_of_week=slot.day_of_week, time=new_time)
        .exclude(id=slot.id)
        .exists()
    ):
        raise HttpError(409, "A slot at that time already exists.")
    slot.time = new_time
    slot.save(update_fields=["time", "updated_at"])
    return _slot(slot)


@router.delete("/{workspace_id}/calendar/slots/{uuid:slot_id}", summary="Delete a slot")
def slot_delete(request, workspace_id: uuid.UUID, slot_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_social_accounts")
    PostingSlot.objects.filter(id=slot_id, social_account__workspace=m.workspace).delete()
    return {"deleted": True}


class ToggleDay(Schema):
    social_account_id: uuid.UUID
    day_of_week: int


@router.post("/{workspace_id}/calendar/slots/toggle-day", summary="Pause or resume every slot on a day")
def slot_toggle_day(request, workspace_id: uuid.UUID, payload: ToggleDay):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_social_accounts")
    account = get_object_or_404(SocialAccount, id=payload.social_account_id, workspace=m.workspace)
    qs = PostingSlot.objects.filter(social_account=account, day_of_week=payload.day_of_week)
    if not qs.exists():
        return {"toggled": False}
    all_active = not qs.filter(is_active=False).exists()
    qs.update(is_active=not all_active)
    return {"toggled": True, "is_active": not all_active}


# ---------------------------------------------------------------------------
# Queues
# ---------------------------------------------------------------------------


def _queue(q: Queue) -> dict:
    return {
        "id": str(q.id),
        "name": q.name,
        "is_active": q.is_active,
        "account": {
            "id": str(q.social_account_id),
            "name": q.social_account.account_name,
            "platform": q.social_account.platform,
        },
        "category": {"id": str(q.category.id), "name": q.category.name} if q.category else None,
        "entry_count": q.entries.count(),
    }


@router.get("/{workspace_id}/calendar/queues", summary="Queues with accounts and categories to create more")
def queues(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    ws = m.workspace
    return {
        "queues": [_queue(q) for q in Queue.objects.for_workspace(ws.id).select_related("social_account", "category")],
        "accounts": [
            {"id": str(a.id), "name": a.account_name, "platform": a.platform}
            for a in SocialAccount.objects.for_workspace(ws.id).filter(
                connection_status=SocialAccount.ConnectionStatus.CONNECTED
            )
        ],
        "categories": [{"id": str(c.id), "name": c.name} for c in ContentCategory.objects.for_workspace(ws.id)],
    }


class QueueIn(Schema):
    name: str
    social_account_id: uuid.UUID
    category_id: uuid.UUID | None = None


@router.post("/{workspace_id}/calendar/queues", summary="Create a queue")
def queue_create(request, workspace_id: uuid.UUID, payload: QueueIn):
    m = scoped(request, workspace_id)
    if not payload.name.strip():
        raise HttpError(400, "Name is required.")
    account = get_object_or_404(SocialAccount, id=payload.social_account_id, workspace=m.workspace)
    category = (
        get_object_or_404(ContentCategory, id=payload.category_id, workspace=m.workspace)
        if payload.category_id
        else None
    )
    q = Queue.objects.create(
        workspace=m.workspace, name=payload.name.strip(), social_account=account, category=category
    )
    return _queue(q)


@router.delete("/{workspace_id}/calendar/queues/{uuid:queue_id}", summary="Delete a queue")
def queue_delete(request, workspace_id: uuid.UUID, queue_id: uuid.UUID):
    m = scoped(request, workspace_id)
    get_object_or_404(Queue, id=queue_id, workspace=m.workspace).delete()
    return {"deleted": True}


def _entry(e: QueueEntry, account_id) -> dict:
    pp = next((x for x in e.post.platform_posts.all() if x.social_account_id == account_id), None)
    return {
        "id": str(e.id),
        "post_id": str(e.post_id),
        "position": e.position,
        "slot": e.assigned_slot_datetime.isoformat() if e.assigned_slot_datetime else None,
        "title": e.post.title,
        "caption": (pp.effective_caption if pp else e.post.caption)[:140],
        "status": pp.status if pp else e.post.status,
        "author": e.post.author.display_name if e.post.author else None,
    }


@router.get("/{workspace_id}/calendar/queues/{uuid:queue_id}", summary="A queue's entries in slot order")
def queue_detail(request, workspace_id: uuid.UUID, queue_id: uuid.UUID):
    m = scoped(request, workspace_id)
    q = get_object_or_404(
        Queue.objects.select_related("social_account", "category"), id=queue_id, workspace=m.workspace
    )
    entries = (
        q.entries.select_related("post__author")
        .prefetch_related("post__platform_posts__social_account")
        .order_by(F("assigned_slot_datetime").asc(nulls_last=True), "position")
    )
    return {"queue": _queue(q), "entries": [_entry(e, q.social_account_id) for e in entries]}


class ReorderIn(Schema):
    entry_ids: list[uuid.UUID]


@router.post("/{workspace_id}/calendar/queues/{uuid:queue_id}/reorder", summary="Reorder a queue")
def queue_reorder(request, workspace_id: uuid.UUID, queue_id: uuid.UUID, payload: ReorderIn):
    m = scoped(request, workspace_id)
    q = get_object_or_404(Queue, id=queue_id, workspace=m.workspace)
    services.reorder_queue(q, [str(x) for x in payload.entry_ids])
    return {"reordered": True}


@router.delete("/{workspace_id}/calendar/queues/{uuid:queue_id}/entries/{uuid:entry_id}", summary="Remove from queue")
def queue_entry_remove(request, workspace_id: uuid.UUID, queue_id: uuid.UUID, entry_id: uuid.UUID):
    m = scoped(request, workspace_id)
    entry = (
        QueueEntry.objects.filter(id=entry_id, queue_id=queue_id, queue__workspace=m.workspace)
        .select_related("post", "queue__social_account")
        .first()
    )
    if entry is not None:
        services.remove_from_queue(entry)
    return {"removed": entry is not None}


@router.post("/{workspace_id}/calendar/queues/{uuid:queue_id}/entries/{uuid:entry_id}/reslot", summary="Next open slot")
def queue_entry_reslot(request, workspace_id: uuid.UUID, queue_id: uuid.UUID, entry_id: uuid.UUID):
    m = scoped(request, workspace_id)
    entry = get_object_or_404(
        QueueEntry.objects.select_related("post", "queue__social_account"),
        id=entry_id,
        queue_id=queue_id,
        queue__workspace=m.workspace,
    )
    try:
        services.reslot_to_next_available(entry)
    except services.QueueFullError as exc:
        raise HttpError(409, "No open slot within the scheduling horizon.") from exc
    return {"reslotted": True}


# ---------------------------------------------------------------------------
# Organization-wide calendar
# ---------------------------------------------------------------------------


@org_router.get("/calendar", summary="Every workspace's chips for a date window")
def org_calendar(request, start: str, end: str, channel: str = "", status: str = "", tag: str = ""):
    ws_ids = list(WorkspaceMembership.objects.filter(user=request.user).values_list("workspace_id", flat=True))
    workspaces = list(Workspace.objects.filter(id__in=ws_ids, is_archived=False).order_by("name"))
    selected = [w for w in request.GET.getlist("workspace") if w]
    shown = [w for w in workspaces if not selected or str(w.id) in selected]
    try:
        start_d, end_d = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except ValueError as exc:
        raise HttpError(400, "start and end must be YYYY-MM-DD") from exc
    if end_d < start_d or (end_d - start_d).days > 62:
        raise HttpError(400, "window must be at most 62 days")
    qs = (
        PlatformPost.objects.filter(post__workspace__in=shown)
        .select_related("post__workspace", "post__author", "social_account")
        .annotate(effective_at=Coalesce("scheduled_at", "post__scheduled_at"))
        .filter(
            effective_at__date__gte=start_d - dt.timedelta(days=1), effective_at__date__lte=end_d + dt.timedelta(days=1)
        )
    )
    if channel:
        try:
            qs = qs.filter(social_account_id=uuid.UUID(channel))
        except ValueError as exc:
            raise HttpError(400, "Invalid channel") from exc
    if status:
        qs = qs.filter(status=status)
    if tag:
        qs = qs.filter(post__tags__contains=[tag])
    palette = ["#0a0a0a", "#525252", "#a3a3a3", "#dc2626", "#2563eb", "#16a34a", "#d97706", "#7c3aed"]
    colors = {str(w.id): (w.primary_color or palette[i % len(palette)]) for i, w in enumerate(workspaces)}
    return {
        "today": timezone.now().date().isoformat(),
        "workspaces": [{"id": str(w.id), "name": w.name, "color": colors[str(w.id)]} for w in workspaces],
        "selected": [str(w.id) for w in shown] if selected else [],
        "accounts": [
            {"id": str(a.id), "name": a.account_name, "platform": a.platform, "workspace_id": str(a.workspace_id)}
            for a in SocialAccount.objects.filter(
                workspace__in=shown, connection_status=SocialAccount.ConnectionStatus.CONNECTED
            ).order_by("platform", "account_name")
        ],
        "tags": sorted(set(Tag.objects.filter(workspace__in=shown).values_list("name", flat=True))),
        "statuses": list(PlatformPost.Status.values),
        "chips": [
            {
                "id": str(pp.id),
                "post_id": str(pp.post_id),
                "workspace_id": str(pp.post.workspace_id),
                "workspace_name": pp.post.workspace.name,
                "color": colors.get(str(pp.post.workspace_id), "#0a0a0a"),
                "at": pp.effective_at.isoformat() if pp.effective_at else None,
                "status": pp.status,
                "platform": pp.social_account.platform,
                "account": {"id": str(pp.social_account_id), "name": pp.social_account.account_name},
                "title": pp.post.title,
                "caption": pp.effective_caption[:140],
            }
            for pp in qs.order_by("effective_at")
            if pp.effective_at
        ],
    }
