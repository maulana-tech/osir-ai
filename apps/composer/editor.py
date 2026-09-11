"""The composer's save pipeline, shared by the Django composer view and the web API.

Both callers build an :class:`EditorPayload` (the Django view from its form
POST, the web API from JSON) and hand it to :func:`save`. Everything the old
``save_post`` view did — per-platform overrides and extras, scheduling and
queueing, approval submission, media, tags, recurrence, the approved-content
revert, version snapshots — lives here once.
"""

from __future__ import annotations

import datetime as dt
import uuid
import zoneinfo
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.common.validators import normalize_tags, parse_and_truncate_tag_string, parse_and_truncate_youtube_tag_string
from apps.social_accounts.models import SocialAccount
from providers.tiktok import VALID_PRIVACY_LEVELS as TIKTOK_PRIVACY_LEVELS

from .models import ContentCategory, PlatformPost, Post, PostMedia, PostTemplate, PostVersion, Tag

QUEUE_FULL_MSG = "No open posting slot within the scheduling horizon — add posting slots or free one up."

ACTIONS = (
    "save_draft",
    "autosave",
    "schedule",
    "publish_now",
    "add_to_queue",
    "add_to_queue_priority",
    "submit_for_approval",
    "resubmit_for_approval",
)

COMMITTED_STATUSES = ("scheduled", "publishing", "published")


class EditorError(Exception):
    """A validation problem the caller shows to the person (HTTP 400)."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)

    @property
    def errors(self) -> dict[str, str]:
        return {self.field: self.message}


@dataclass
class AccountInput:
    id: str
    title: str | None = None
    caption: str | None = None
    first_comment: str | None = None
    #: Platform panel values (YouTube / Pinterest / TikTok). ``None`` means the
    #: panel was not part of the submission, so stored extras are left alone.
    extra: dict[str, Any] | None = None


@dataclass
class EditorPayload:
    action: str = "save_draft"
    title: str = ""
    caption: str = ""
    first_comment: str = ""
    internal_notes: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: str | None = None
    accounts: list[AccountInput] = field(default_factory=list)
    #: When the composer was opened for one account (``?account=``), only that
    #: account's row may be created / deleted / re-timed.
    account_scope: str | None = None
    #: Ordered media assets. ``None`` = leave attachments untouched.
    media_asset_ids: list[str] | None = None
    scheduled_date: dt.date | None = None
    scheduled_time: dt.time | None = None
    queue_id: str | None = None
    recurring: dict[str, Any] | None = None


def _truthy(v: Any) -> bool:
    return v is True or v == "true"


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError):
        return False
    return True


# ---------------------------------------------------------------------------
# Platform extras
# ---------------------------------------------------------------------------


def normalize_platform_extra(platform: str, extra: dict[str, Any], existing: dict[str, Any] | None) -> dict | None:
    """Turn a platform panel submission into the stored ``platform_extra`` shape.

    Accepts both the web API's typed values and the Django form's strings.
    Returns ``None`` for platforms without a panel.
    """
    existing = existing or {}
    if platform == "youtube":
        tags = extra.get("tags", "")
        if isinstance(tags, list):
            tags = ",".join(str(t) for t in tags)
        privacy = extra.get("privacy_status") or "public"
        if privacy not in ("public", "unlisted", "private"):
            privacy = "public"
        return {
            "privacy_status": privacy,
            "self_declared_made_for_kids": _truthy(extra.get("made_for_kids")),
            "tags": parse_and_truncate_youtube_tag_string(tags or ""),
            "thumbnail_asset_id": _clean(extra.get("thumbnail_asset_id")),
        }
    if platform == "pinterest":
        return {
            "board_id": _clean(extra.get("board_id")) or existing.get("board_id") or None,
            "link_url": _clean(extra.get("link_url")),
            "alt_text": _clean(extra.get("alt_text")),
            "tag_products": _clean(extra.get("tag_products")),
            "allow_comments": _truthy(extra.get("allow_comments")),
            "show_similar_products": _truthy(extra.get("show_similar_products")),
            "cover_image_asset_id": _clean(extra.get("cover_image_asset_id")),
        }
    if platform == "tiktok":
        privacy = _clean(extra.get("privacy_level")) or ""
        if privacy not in TIKTOK_PRIVACY_LEVELS:
            # An empty/invalid submit must not wipe a previously saved choice.
            privacy = existing.get("privacy_level", "")
        out: dict[str, Any] = {
            "disable_comment": not _truthy(extra.get("allow_comment")),
            "disable_duet": not _truthy(extra.get("allow_duet")),
            "disable_stitch": not _truthy(extra.get("allow_stitch")),
            "brand_organic_toggle": _truthy(extra.get("brand_organic")),
            "brand_content_toggle": _truthy(extra.get("brand_content")),
            "is_aigc": _truthy(extra.get("is_aigc")),
        }
        if privacy:
            out["privacy_level"] = privacy
        cover = extra.get("video_cover_timestamp_ms")
        if cover is not None and str(cover).strip() != "":
            try:
                cover_ms = int(cover)
            except (ValueError, TypeError):
                cover_ms = -1
            if cover_ms >= 0:
                out["video_cover_timestamp_ms"] = cover_ms
        return out
    return None


def _validate_pinterest_boards(post: Post | None, workspace, accounts: list[AccountInput]) -> None:
    by_id = {a.id: a for a in accounts if _is_uuid(a.id)}
    ids = list(by_id)
    if not ids:
        return
    for account in SocialAccount.objects.filter(id__in=ids, workspace=workspace, platform="pinterest"):
        acc = by_id[str(account.id)]
        board = _clean((acc.extra or {}).get("board_id"))
        if not board and post is not None and post.pk:
            board = (
                PlatformPost.objects.filter(post=post, social_account=account)
                .values_list("platform_extra__board_id", flat=True)
                .first()
                or ""
            )
        if not board:
            raise EditorError("pinterest_board", f"Select a Pinterest board for {account.account_name}.")


# ---------------------------------------------------------------------------
# Platform post sync
# ---------------------------------------------------------------------------


def remove_deselected_platform_posts(post: Post, selected_ids: list[str], account_scope: str | None) -> None:
    """Delete rows the person deselected; never published/publishing ones, never outside the scope."""
    qs = post.platform_posts.exclude(social_account_id__in=selected_ids)
    if account_scope:
        qs = qs.filter(social_account_id=uuid.UUID(account_scope))
    qs.exclude(status__in=PlatformPost.PROTECTED_STATUSES).delete()


def scoped_platform_post_ids(post: Post, account_scope: str | None):
    if not account_scope:
        return None
    return list(post.platform_posts.filter(social_account_id=uuid.UUID(account_scope)).values_list("id", flat=True))


def sync_platform_posts(post: Post, workspace, accounts: list[AccountInput], account_scope, initial_status=None):
    """Create/update a PlatformPost per selected account with its overrides and extras."""
    selected_ids = [a.id for a in accounts if _is_uuid(a.id)]
    remove_deselected_platform_posts(post, selected_ids, account_scope)
    for acc in accounts:
        if not _is_uuid(acc.id):
            continue
        try:
            account = SocialAccount.objects.get(id=acc.id, workspace=workspace)
        except SocialAccount.DoesNotExist:
            continue
        defaults = {"status": initial_status} if initial_status else {}
        pp, _created = PlatformPost.objects.get_or_create(post=post, social_account=account, defaults=defaults)
        pp.platform_specific_title = _clean(acc.title)
        pp.platform_specific_caption = _clean(acc.caption)
        pp.platform_specific_first_comment = _clean(acc.first_comment)
        if acc.extra is not None:
            normalized = normalize_platform_extra(account.platform, acc.extra, pp.platform_extra)
            if normalized is not None:
                pp.platform_extra = normalized
        pp.save()


def transition_post_children(post: Post, target: str, *, allow_via_draft=True, only=None):
    """Move every (or the ``only``) child to ``target``; returns ``(moved, skipped)``."""
    children = list(post.platform_posts.all())
    if only is not None:
        only_ids = {str(x) for x in only}
        children = [pp for pp in children if str(pp.id) in only_ids]
    moved, skipped = [], []
    for pp in children:
        if pp.status == target:
            moved.append(pp)
            continue
        try:
            if pp.can_transition_to(target):
                pp.transition_to(target)
            elif allow_via_draft and pp.can_transition_to("draft") and target != "draft":
                pp.transition_to("draft")
                if pp.can_transition_to(target):
                    pp.transition_to(target)
                else:
                    skipped.append(pp)
                    continue
            else:
                skipped.append(pp)
                continue
            pp.save(update_fields=["status", "published_at", "updated_at"])
            moved.append(pp)
        except ValueError:
            skipped.append(pp)
    return moved, skipped


def base_content_snapshot(post: Post):
    return (post.title, post.caption, post.first_comment, tuple(post.tags or []))


def revert_approved_to_review(post: Post):
    """Editing an approved post's content sends it back for re-approval."""
    reverted = []
    for pp in post.platform_posts.all():
        if pp.status == "approved" and pp.can_transition_to("pending_review"):
            pp.transition_to("pending_review")
            pp.save(update_fields=["status", "published_at", "updated_at"])
            reverted.append(pp)
    return reverted


def platform_status_map(post: Post) -> dict[str, str]:
    return {str(pp.id): pp.status for pp in post.platform_posts.all()}


def combine_schedule_dt(workspace, sched_date, sched_time):
    if not (sched_date and sched_time):
        return None
    tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
    return dt.datetime.combine(sched_date, sched_time).replace(tzinfo=tz)


def post_is_committed(post: Post | None) -> bool:
    return post is not None and (
        post.scheduled_at is not None
        or (bool(post.pk) and post.platform_posts.filter(status__in=COMMITTED_STATUSES).exists())
    )


def capture_proposed_publish_at(post: Post, workspace, payload: EditorPayload, *, clear_when_blank=True) -> None:
    """The Schedule panel doubles as the proposed-time picker while a post is still a draft."""
    if post_is_committed(post):
        return
    proposed = combine_schedule_dt(workspace, payload.scheduled_date, payload.scheduled_time)
    if proposed is None and not clear_when_blank:
        return
    post.proposed_publish_at = proposed


def save_version(post: Post, user) -> None:
    snapshot = {
        "title": post.title,
        "caption": post.caption,
        "first_comment": post.first_comment,
        "internal_notes": post.internal_notes,
        "tags": post.tags,
        "status": post.status,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "platform_posts": [
            {
                "social_account_id": str(pp.social_account_id),
                "platform": pp.social_account.platform,
                "title_override": pp.platform_specific_title,
                "caption_override": pp.platform_specific_caption,
                "first_comment_override": pp.platform_specific_first_comment,
                "platform_extra": pp.platform_extra or {},
            }
            for pp in post.platform_posts.select_related("social_account")
        ],
        "media": [
            {"media_asset_id": str(pm.media_asset_id), "position": pm.position, "alt_text": pm.alt_text}
            for pm in post.media_attachments.all()
        ],
    }
    PostVersion.objects.create(post=post, version_number=post.versions.count() + 1, snapshot=snapshot, created_by=user)


def sync_tags_to_model(workspace, tag_names) -> None:
    if not tag_names:
        return
    existing = set(Tag.objects.for_workspace(workspace.id).filter(name__in=tag_names).values_list("name", flat=True))
    new = [Tag(workspace=workspace, name=n) for n in tag_names if n not in existing]
    if new:
        Tag.objects.bulk_create(new, ignore_conflicts=True)


def sync_media(post: Post, workspace, ordered_ids: list[str]) -> bool:
    """Make ``post.media_attachments`` match ``ordered_ids`` (workspace + shared assets only).

    Returns whether the attachment list changed (a media edit counts as a
    content edit for the approved-content revert).
    """
    from apps.media_library.models import MediaAsset

    wanted = []
    seen: set[str] = set()
    for raw in ordered_ids:
        if _is_uuid(raw) and str(uuid.UUID(str(raw))) not in seen:
            seen.add(str(uuid.UUID(str(raw))))
            wanted.append(str(uuid.UUID(str(raw))))
    valid = {
        str(a)
        for a in MediaAsset.objects.for_workspace_with_shared(workspace.id, workspace.organization_id)
        .filter(id__in=wanted)
        .values_list("id", flat=True)
    }
    wanted = [w for w in wanted if w in valid]
    attachments = list(post.media_attachments.order_by("position"))
    existing = {str(pm.media_asset_id): pm for pm in attachments}
    post.media_attachments.exclude(media_asset_id__in=wanted).delete()
    for position, asset_id in enumerate(wanted):
        pm = existing.get(asset_id)
        if pm is None:
            PostMedia.objects.create(post=post, media_asset_id=asset_id, position=position)
        elif pm.position != position:
            pm.position = position
            pm.save(update_fields=["position"])
    return [str(pm.media_asset_id) for pm in attachments] != wanted


def resolve_queues(queue_id, workspace, account_ids: list[str]):
    from apps.calendar.models import Queue

    if queue_id:
        q = Queue.objects.filter(id=queue_id, workspace=workspace, is_active=True).first()
        return [q] if q else []
    if not account_ids:
        return []
    seen: set = set()
    unique = []
    for q in Queue.objects.filter(workspace=workspace, is_active=True, social_account_id__in=account_ids).order_by(
        "created_at"
    ):
        if q.social_account_id in seen:
            continue
        seen.add(q.social_account_id)
        unique.append(q)
    return unique


def resolve_template_data(template_id, workspace):
    """``?template=`` → template_data dict, for a built-in numeric id or a saved PostTemplate uuid."""
    if not template_id:
        return None
    try:
        numeric_id: int | None = int(template_id)
    except (TypeError, ValueError):
        numeric_id = None
    if numeric_id is not None:
        from apps.composer.builtin_templates import TEMPLATES as BUILTIN_TEMPLATES

        for tpl in BUILTIN_TEMPLATES:
            if tpl.get("id") == numeric_id:
                return {"caption": tpl.get("body", ""), "tags": list(tpl.get("tags", []))}
        return None
    try:
        return PostTemplate.objects.get(id=template_id, workspace=workspace).template_data
    except (PostTemplate.DoesNotExist, ValidationError):
        return None


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def check_can_edit(post: Post, user, perms: dict) -> None:
    if post.author != user and not perms.get("edit_others_posts", False):
        raise PermissionDenied("You do not have permission to edit this post.")


def _apply_fields(post: Post, workspace, payload: EditorPayload) -> None:
    post.title = payload.title or ""
    post.caption = payload.caption or ""
    post.first_comment = payload.first_comment or ""
    post.internal_notes = payload.internal_notes or ""
    try:
        post.tags = normalize_tags(payload.tags or [])
    except ValueError as exc:
        raise EditorError("tags", str(exc)) from exc
    if payload.category_id:
        post.category = ContentCategory.objects.filter(id=payload.category_id, workspace=workspace).first()
    else:
        post.category = None


def _save_recurrence(post: Post, rec: dict[str, Any]) -> None:
    from apps.calendar.models import RecurrenceRule

    frequency = rec.get("frequency") or "weekly"
    if frequency not in RecurrenceRule.Frequency.values:
        frequency = "weekly"
    try:
        interval = max(1, int(rec.get("interval") or 1))
    except (ValueError, TypeError):
        interval = 1
    end_date = None
    if rec.get("end_date"):
        try:
            end_date = dt.date.fromisoformat(str(rec["end_date"]))
        except (ValueError, TypeError):
            end_date = None
    RecurrenceRule.objects.update_or_create(
        post=post, defaults={"frequency": frequency, "interval": interval, "end_date": end_date, "is_active": True}
    )


def _queue(post: Post, workspace, user, payload: EditorPayload, *, priority: bool) -> Post:
    from apps.calendar.services import QueueFullError, add_to_queue

    queues = resolve_queues(payload.queue_id, workspace, [a.id for a in payload.accounts if _is_uuid(a.id)])
    if not queues:
        raise EditorError("queue", "No active queue found for the selected channel.")
    post.proposed_publish_at = None
    post.save()
    if payload.media_asset_ids is not None:
        sync_media(post, workspace, payload.media_asset_ids)
    sync_platform_posts(post, workspace, payload.accounts, payload.account_scope, initial_status="draft")
    try:
        with transaction.atomic():
            for q in queues:
                add_to_queue(post, q, priority=priority)
            transition_post_children(post, "scheduled", only=scoped_platform_post_ids(post, payload.account_scope))
    except QueueFullError as exc:
        raise EditorError("queue", QUEUE_FULL_MSG) from exc
    sync_tags_to_model(workspace, post.tags)
    save_version(post, user)
    return post


def _approval(post: Post, workspace, user, payload: EditorPayload, *, resubmit: bool) -> Post:
    from apps.approvals.services import resubmit_post, submit_for_review

    capture_proposed_publish_at(post, workspace, payload, clear_when_blank=False)
    post.save()
    if payload.media_asset_ids is not None:
        sync_media(post, workspace, payload.media_asset_ids)
    sync_platform_posts(post, workspace, payload.accounts, payload.account_scope, initial_status="draft")
    sync_tags_to_model(workspace, post.tags)
    save_version(post, user)
    (resubmit_post if resubmit else submit_for_review)(post, user, workspace)
    return post


def autosave(post: Post | None, workspace, user, payload: EditorPayload) -> Post:
    """The 30-second autosave: fields, selection and media only. No version, no schedule."""
    orig = base_content_snapshot(post) if post is not None else None
    if post is None:
        post = Post(workspace=workspace, author=user)
    post.title = payload.title or ""
    post.caption = payload.caption or ""
    post.first_comment = payload.first_comment or ""
    post.internal_notes = payload.internal_notes or ""
    post.tags = parse_and_truncate_tag_string(",".join(payload.tags or []))
    post.save()
    media_changed = payload.media_asset_ids is not None and sync_media(post, workspace, payload.media_asset_ids)
    selected = [a.id for a in payload.accounts if _is_uuid(a.id)]
    remove_deselected_platform_posts(post, selected, payload.account_scope)
    for acc_id in selected:
        PlatformPost.objects.get_or_create(post=post, social_account_id=acc_id)
    if media_changed or (orig is not None and base_content_snapshot(post) != orig):
        revert_approved_to_review(post)
    return post


def save(post: Post | None, workspace, user, perms: dict, payload: EditorPayload, *, orig_content=None) -> Post:
    """Persist the composer state and run ``payload.action``. Returns the post.

    ``orig_content`` is the :func:`base_content_snapshot` taken before the
    caller touched ``post`` (a Django ModelForm mutates its instance during
    validation); it defaults to the post's current content.

    Raises :class:`EditorError` for input problems and ``PermissionDenied`` when
    the action needs a permission the caller lacks.
    """
    if payload.action not in ACTIONS:
        payload.action = "save_draft"
    if payload.action == "autosave":
        return autosave(post, workspace, user, payload)

    is_new = post is None
    if orig_content is None and post is not None:
        orig_content = base_content_snapshot(post)
    if post is None:
        post = Post(workspace=workspace, author=user)
    _apply_fields(post, workspace, payload)
    _validate_pinterest_boards(None if is_new else post, workspace, payload.accounts)

    action = payload.action
    if action == "add_to_queue":
        return _queue(post, workspace, user, payload, priority=False)
    if action == "add_to_queue_priority":
        return _queue(post, workspace, user, payload, priority=True)
    if action == "submit_for_approval":
        return _approval(post, workspace, user, payload, resubmit=False)
    if action == "resubmit_for_approval":
        return _approval(post, workspace, user, payload, resubmit=True)

    pending_target = None
    initial_status = "draft"
    propagate_dt = None
    if action == "schedule":
        aware_dt = combine_schedule_dt(workspace, payload.scheduled_date, payload.scheduled_time)
        if aware_dt is None:
            raise EditorError("schedule", "Date and time required.")
        if aware_dt <= timezone.now():
            raise EditorError("schedule", "Scheduled time must be in the future.")
        post.scheduled_at = aware_dt
        post.proposed_publish_at = None
        propagate_dt = aware_dt
        pending_target = initial_status = "scheduled"
    elif action == "publish_now":
        if not perms.get("publish_directly", False):
            raise PermissionDenied("You do not have permission to publish directly.")
        now = timezone.now()
        post.scheduled_at = now
        post.proposed_publish_at = None
        propagate_dt = now
        pending_target = initial_status = "scheduled"
    else:  # save_draft
        capture_proposed_publish_at(post, workspace, payload)

    post.save()
    media_changed = payload.media_asset_ids is not None and sync_media(post, workspace, payload.media_asset_ids)
    sync_tags_to_model(workspace, post.tags)
    if payload.recurring and action == "schedule" and post.scheduled_at:
        _save_recurrence(post, payload.recurring)

    sync_platform_posts(post, workspace, payload.accounts, payload.account_scope, initial_status=initial_status)

    scoped_ids = scoped_platform_post_ids(post, payload.account_scope)
    if propagate_dt is not None:
        qs = post.platform_posts.exclude(status__in=PlatformPost.PROTECTED_STATUSES)
        if scoped_ids is not None:
            qs = qs.filter(id__in=scoped_ids)
        qs.update(scheduled_at=propagate_dt)

    content_changed = media_changed or (orig_content is not None and base_content_snapshot(post) != orig_content)
    reverted_ids = {str(pp.id) for pp in revert_approved_to_review(post)} if content_changed else set()

    if pending_target:
        if reverted_ids:
            candidates = scoped_ids if scoped_ids is not None else [pp.id for pp in post.platform_posts.all()]
            only = [pid for pid in candidates if str(pid) not in reverted_ids]
        else:
            only = scoped_ids
        transition_post_children(post, pending_target, only=only)

    save_version(post, user)
    return post


# ---------------------------------------------------------------------------
# Single-child transition (per-account chip)
# ---------------------------------------------------------------------------

APPROVAL_STATES = {"approved", "pending_review", "pending_client", "changes_requested", "rejected"}


def transition_child(pp: PlatformPost, target: str, perms: dict) -> PlatformPost:
    """Move one PlatformPost; mirrors the composer's permission rules."""
    if target in ("scheduled", "publishing") and not perms.get("publish_directly", False):
        raise PermissionDenied("You do not have permission to schedule this post.")
    if target in APPROVAL_STATES and not perms.get("approve_posts", False) and target != "pending_review":
        raise PermissionDenied("You do not have permission to make approval decisions.")
    if pp.status == target:
        return pp
    pp.transition_to(target)  # ValueError on an invalid move
    pp.save(update_fields=["status", "published_at", "updated_at"])
    if target in COMMITTED_STATUSES and pp.post.proposed_publish_at is not None:
        pp.post.proposed_publish_at = None
        pp.post.save(update_fields=["proposed_publish_at", "updated_at"])
    return pp


def delete_post(post: Post, account_id: str | None) -> None:
    """Delete the post, or just one account's row (and the post if it was the last)."""
    if account_id:
        pp = post.platform_posts.filter(social_account_id=uuid.UUID(account_id)).first()
        if pp is None:
            raise EditorError("account", "No such platform post.")
        pp.delete()
        if not post.platform_posts.exists():
            post.delete()
    else:
        post.delete()


def save_as_template(post: Post, workspace, user, name: str, description: str) -> PostTemplate:
    name = (name or "").strip() or f"Template from {post.caption_snippet or 'post'}"
    return PostTemplate.objects.create(
        workspace=workspace,
        name=name,
        description=(description or "").strip(),
        template_data={
            "caption": post.caption,
            "first_comment": post.first_comment,
            "category_id": str(post.category_id) if post.category_id else None,
            "tags": post.tags,
            "platform_account_ids": [str(pp.social_account_id) for pp in post.platform_posts.all()],
            "media_asset_ids": [str(pm.media_asset_id) for pm in post.media_attachments.all()],
        },
        created_by=user,
    )


def next_category_position(workspace) -> int:
    m = ContentCategory.objects.for_workspace(workspace.id).aggregate(models.Max("position"))["position__max"]
    return (m or 0) + 1
