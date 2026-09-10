"""Calendar data for the Publish page: one flat window of chips and open slots.

The UI lays out month / week / day itself, so the API only answers "what is
in this date range, in this display timezone".
"""

from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo
from collections import defaultdict

from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.calendar.models import CustomCalendarEvent, PostingSlot
from apps.calendar.services import RescheduleDeniedError, reschedule_platform_post
from apps.composer.models import ContentCategory, PlatformPost, Post, Tag
from apps.social_accounts.models import SocialAccount
from apps.webapi.common import scoped

router = Router(tags=["calendar"])

MAX_WINDOW_DAYS = 62


def _tz(name: str | None, fallback: str) -> str:
    for candidate in (name, fallback):
        if not candidate:
            continue
        try:
            zoneinfo.ZoneInfo(candidate)
            return candidate
        except (ValueError, zoneinfo.ZoneInfoNotFoundError):
            continue
    return "UTC"


def _parse_date(value: str | None, default: dt.date) -> dt.date:
    if not value:
        return default
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise HttpError(400, f"Invalid date: {value}") from exc


def _uuids(values: list[str]) -> list[uuid.UUID]:
    out = []
    for v in values:
        try:
            out.append(uuid.UUID(v))
        except (ValueError, TypeError):
            continue
    return out


def _chip(pp: PlatformPost) -> dict:
    post = pp.post
    effective_at = getattr(pp, "effective_at", None) or pp.scheduled_at or post.scheduled_at
    return {
        "id": str(pp.id),
        "post_id": str(post.id),
        "at": effective_at.isoformat() if effective_at else None,
        "status": pp.status,
        "platform": pp.social_account.platform,
        "account": {"id": str(pp.social_account_id), "name": pp.social_account.account_name},
        "title": post.title,
        "caption": pp.effective_caption[:140],
        "author": post.author.display_name if post.author is not None else None,
        "is_reschedulable": pp.is_reschedulable,
        "publish_error": pp.publish_error or "",
    }


@router.get("/{workspace_id}/calendar", summary="Chips and open slots for a date window")
def calendar(
    request,
    workspace_id: uuid.UUID,
    start: str | None = None,
    end: str | None = None,
    tz: str | None = None,
):
    membership = scoped(request, workspace_id)
    workspace = membership.workspace
    ws_tz_name = workspace.effective_timezone or "UTC"
    display_tz_name = _tz(tz, ws_tz_name)
    display_tz = zoneinfo.ZoneInfo(display_tz_name)
    ws_tz = zoneinfo.ZoneInfo(ws_tz_name)

    today = timezone.now().astimezone(display_tz).date()
    start_date = _parse_date(start, today.replace(day=1))
    end_date = _parse_date(end, start_date + dt.timedelta(days=41))
    if end_date < start_date:
        raise HttpError(400, "end must be on or after start")
    if (end_date - start_date).days > MAX_WINDOW_DAYS:
        raise HttpError(400, f"window may not exceed {MAX_WINDOW_DAYS} days")

    # Repeatable filters (?channel=a&channel=b …)
    channels = _uuids(request.GET.getlist("channel"))
    statuses = [s for s in request.GET.getlist("status") if s in PlatformPost.Status.values]
    platforms = request.GET.getlist("platform")
    tags = request.GET.getlist("tag")

    qs = (
        PlatformPost.objects.filter(post__workspace_id=workspace_id)
        .select_related("post", "post__author", "social_account")
        .annotate(effective_at=Coalesce("scheduled_at", "post__scheduled_at"))
        .filter(
            effective_at__date__gte=start_date - dt.timedelta(days=1),
            effective_at__date__lte=end_date + dt.timedelta(days=1),
        )
    )
    if channels:
        qs = qs.filter(social_account_id__in=channels)
    if statuses:
        qs = qs.filter(status__in=statuses)
    if platforms:
        qs = qs.filter(social_account__platform__in=platforms)
    if tags:
        tag_q = Q()
        for tag in tags:
            tag_q |= Q(post__tags__contains=[tag])
        qs = qs.filter(tag_q)
    chips = list(qs.order_by("effective_at"))

    # Open posting-slot occurrences: a slot is "taken" when a chip sits at that exact minute.
    now = timezone.now()
    taken = set()
    for pp in chips:
        if pp.effective_at:
            local = pp.effective_at.astimezone(display_tz)
            taken.add((pp.social_account_id, local.date(), local.hour, local.minute))
    slots_qs = PostingSlot.objects.filter(
        social_account__workspace=workspace,
        social_account__connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        is_active=True,
    ).select_related("social_account")
    if channels:
        slots_qs = slots_qs.filter(social_account_id__in=channels)
    dates_by_weekday: dict[int, list[dt.date]] = defaultdict(list)
    d = start_date - dt.timedelta(days=1)
    while d <= end_date + dt.timedelta(days=1):
        dates_by_weekday[d.weekday()].append(d)
        d += dt.timedelta(days=1)
    open_slots = []
    for slot in slots_qs:
        for day in dates_by_weekday.get(slot.day_of_week, []):
            ws_dt = dt.datetime.combine(day, slot.time, tzinfo=ws_tz)
            local = ws_dt.astimezone(display_tz)
            if not (start_date <= local.date() <= end_date):
                continue
            if (slot.social_account_id, local.date(), local.hour, local.minute) in taken:
                continue
            open_slots.append(
                {
                    "at": ws_dt.isoformat(),
                    "account": {"id": str(slot.social_account_id), "name": slot.social_account.account_name},
                    "platform": slot.social_account.platform,
                    "compose_date": ws_dt.strftime("%Y-%m-%d"),
                    "compose_time": ws_dt.strftime("%H:%M"),
                    "is_past": ws_dt <= now,
                }
            )

    drafts = (
        Post.objects.for_workspace(workspace_id)
        .filter(platform_posts__status="draft", scheduled_at__isnull=True)
        .distinct()
        .order_by("-updated_at")[:10]
    )

    accounts = SocialAccount.objects.for_workspace(workspace_id).order_by("platform", "account_name")
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "display_timezone": display_tz_name,
        "workspace_timezone": ws_tz_name,
        "today": today.isoformat(),
        "can_publish_directly": bool(membership.effective_permissions.get("publish_directly")),
        "can_edit_others": bool(membership.effective_permissions.get("edit_others_posts")),
        "chips": [_chip(pp) for pp in chips],
        "open_slots": open_slots,
        "events": [
            {
                "id": str(e.id),
                "title": e.title,
                "description": e.description,
                "start_date": e.start_date.isoformat(),
                "end_date": e.end_date.isoformat(),
                "color": e.color,
            }
            for e in CustomCalendarEvent.objects.filter(
                workspace=workspace, start_date__lte=end_date, end_date__gte=start_date
            ).order_by("start_date")
        ],
        "unscheduled_drafts": [
            {"id": str(p.id), "title": p.title, "caption": p.caption[:140], "updated_at": p.updated_at.isoformat()}
            for p in drafts
        ],
        "filters": {
            "channels": [
                {
                    "id": str(a.id),
                    "name": a.account_name,
                    "platform": a.platform,
                    "connected": a.connection_status == SocialAccount.ConnectionStatus.CONNECTED,
                }
                for a in accounts
            ],
            "statuses": list(PlatformPost.Status.values),
            "tags": sorted(Tag.objects.for_workspace(workspace_id).values_list("name", flat=True)),
            "categories": [
                {"id": str(c.id), "name": c.name} for c in ContentCategory.objects.for_workspace(workspace_id)
            ],
        },
    }


class RescheduleRequest(Schema):
    platform_post_id: uuid.UUID
    new_local: str  # "YYYY-MM-DDTHH:MM" wall-clock in ``tz``
    tz: str | None = None


@router.post("/{workspace_id}/calendar/reschedule", summary="Move a chip (drag-and-drop)")
def reschedule(request, workspace_id: uuid.UUID, payload: RescheduleRequest):
    membership = scoped(request, workspace_id)
    workspace = membership.workspace
    tz_name = _tz(payload.tz, workspace.effective_timezone or "UTC")
    try:
        new_dt = dt.datetime.fromisoformat(payload.new_local)
    except ValueError as exc:
        raise HttpError(400, "new_local must be YYYY-MM-DDTHH:MM") from exc
    if new_dt.tzinfo is None:
        new_dt = new_dt.replace(tzinfo=zoneinfo.ZoneInfo(tz_name))

    try:
        pp = PlatformPost.objects.select_related("post", "social_account").get(
            id=payload.platform_post_id, post__workspace_id=workspace_id
        )
    except PlatformPost.DoesNotExist as exc:
        raise HttpError(404, "Post not found") from exc
    try:
        reschedule_platform_post(pp, new_dt, user=request.user, perms=membership.effective_permissions)
    except RescheduleDeniedError as exc:
        raise HttpError(403, str(exc)) from exc
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return _chip(pp)
