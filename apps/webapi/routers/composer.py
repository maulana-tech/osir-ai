"""Composer: the post editor, ideas board, templates, categories, tags, feeds, CSV import."""

from __future__ import annotations

import contextlib
import datetime as dt
import uuid
import zoneinfo
from typing import Any

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from ninja import File, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.approvals.models import ApprovalAction
from apps.calendar.models import Queue, RecurrenceRule
from apps.common.validators import parse_and_truncate_tag_string
from apps.composer import csv_import, editor, feeds, ideas, platform_info, unsplash
from apps.composer.builtin_templates import CATEGORIES as TEMPLATE_CATEGORIES
from apps.composer.builtin_templates import get_all_templates, get_featured_templates
from apps.composer.models import ContentCategory, Feed, Idea, IdeaGroup, Post, PostTemplate, Tag
from apps.composer.services import clone_post
from apps.media_library.models import MediaAsset
from apps.social_accounts.models import SocialAccount
from apps.webapi.common import require_perm, scoped

router = Router(tags=["composer"])


def _perms(m) -> dict:
    return m.effective_permissions


def _post(workspace, post_id) -> Post:
    return get_object_or_404(Post, id=post_id, workspace=workspace)


def _editable(post: Post, request, m) -> None:
    try:
        editor.check_can_edit(post, request.user, _perms(m))
    except PermissionDenied as exc:
        raise HttpError(403, str(exc)) from exc


def _account(a: SocialAccount) -> dict:
    cfg = dict(a.field_config)
    cfg["supports_first_comment"] = a.supports_first_comment()
    return {
        "id": str(a.id),
        "platform": a.platform,
        "name": a.account_name or a.account_handle,
        "handle": a.account_handle,
        "avatar_url": a.avatar_url or "",
        "char_limit": a.char_limit,
        "escaped_chars": a.escaped_chars,
        **cfg,
    }


def _asset_ref(a: MediaAsset) -> dict:
    return {
        "id": str(a.id),
        "url": a.file.url if a.file else "",
        "thumbnail_url": a.thumbnail.url if a.thumbnail else None,
        "filename": a.filename,
        "media_type": a.media_type,
        "width": a.width,
        "height": a.height,
        "duration": a.duration,
    }


def _local(dt_value, workspace) -> tuple[str, str]:
    tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
    local = dt_value.astimezone(tz)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def _post_detail(post: Post, workspace, user, perms) -> dict:
    pps = list(post.platform_posts.select_related("social_account"))
    extras = {str(pp.social_account_id): dict(pp.platform_extra or {}) for pp in pps}
    # Resolve thumbnail / cover assets so the panels can show what was picked.
    asset_ids = [v for e in extras.values() for v in (e.get("thumbnail_asset_id"), e.get("cover_image_asset_id")) if v]
    if asset_ids:
        urls = {
            str(a.id): (a.thumbnail.url if a.thumbnail else (a.file.url if a.file else ""))
            for a in MediaAsset.objects.filter(id__in=asset_ids, workspace=workspace)
        }
        for e in extras.values():
            if e.get("thumbnail_asset_id") in urls:
                e["thumbnail_url"] = urls[e["thumbnail_asset_id"]]
            if e.get("cover_image_asset_id") in urls:
                e["cover_image_url"] = urls[e["cover_image_asset_id"]]
    history = list(ApprovalAction.objects.filter(post=post).select_related("user").order_by("-created_at")[:50])
    feedback = next((a for a in history if a.action in ("changes_requested", "rejected") and a.comment), None)
    prefill = post.scheduled_at or post.proposed_publish_at
    sched_date = sched_time = ""
    if prefill:
        sched_date, sched_time = _local(prefill, workspace)
    committed = editor.post_is_committed(post)
    statuses = {pp.status for pp in pps}
    rec = RecurrenceRule.objects.filter(post=post, is_active=True).first()
    return {
        "id": str(post.id),
        "title": post.title,
        "caption": post.caption,
        "first_comment": post.first_comment,
        "internal_notes": post.internal_notes,
        "tags": list(post.tags or []),
        "category_id": str(post.category_id) if post.category_id else None,
        "status": post.status,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "proposed_publish_at": post.proposed_publish_at.isoformat() if post.proposed_publish_at else None,
        "scheduled_date": sched_date,
        "scheduled_time": sched_time,
        "schedule_is_proposed": bool(prefill) and post.scheduled_at is None,
        "is_committed": committed,
        "read_only": bool(pps) and statuses <= {"published", "publishing"},
        "can_edit": post.author == user or bool(perms.get("edit_others_posts")),
        "author": post.author.display_name if post.author else None,
        "updated_at": post.updated_at.isoformat(),
        "platform_posts": [
            {
                "id": str(pp.id),
                "social_account_id": str(pp.social_account_id),
                "platform": pp.social_account.platform,
                "status": pp.status,
                "title": pp.platform_specific_title,
                "caption": pp.platform_specific_caption,
                "first_comment": pp.platform_specific_first_comment,
                "extra": extras[str(pp.social_account_id)],
                "scheduled_at": pp.scheduled_at.isoformat() if pp.scheduled_at else None,
                "publish_error": pp.publish_error,
                "first_comment_status": pp.first_comment_status,
                "first_comment_error": pp.first_comment_error,
                "platform_post_id": pp.platform_post_id,
            }
            for pp in pps
        ],
        "media": [
            {**_asset_ref(pm.media_asset), "position": pm.position, "alt_text": pm.alt_text}
            for pm in post.media_attachments.select_related("media_asset").order_by("position")
        ],
        "approval_history": [
            {
                "action": a.action,
                "user": a.user.display_name if a.user else None,
                "comment": a.comment,
                "created_at": a.created_at.isoformat(),
            }
            for a in history
        ],
        "latest_feedback": {"action": feedback.action, "comment": feedback.comment} if feedback else None,
        "show_submit": workspace.approval_workflow_mode != "none"
        and not (statuses & {"changes_requested", "rejected", "approved"}),
        "show_resubmit": bool(statuses & {"changes_requested", "rejected", "approved"}),
        "versions_count": post.versions.count(),
        "recurrence": {
            "frequency": rec.frequency,
            "interval": rec.interval,
            "end_date": rec.end_date.isoformat() if rec.end_date else "",
        }
        if rec
        else None,
    }


def _summary(post: Post) -> dict:
    return {
        "id": str(post.id),
        "status": post.status,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "proposed_publish_at": post.proposed_publish_at.isoformat() if post.proposed_publish_at else None,
        "platform_statuses": editor.platform_status_map(post),
        "updated_at": post.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Composer page data
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/composer/context", summary="Everything the composer page needs")
def context(
    request,
    workspace_id: uuid.UUID,
    post_id: uuid.UUID | None = None,
    account: str = "",
    template: str = "",
    scheduled_date: str = "",
    scheduled_time: str = "",
):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    ws = m.workspace
    perms = _perms(m)
    accounts = SocialAccount.objects.for_workspace(ws.id).filter(
        connection_status=SocialAccount.ConnectionStatus.CONNECTED
    )
    account_scope = account if editor._is_uuid(account) else ""
    if account_scope:
        accounts = accounts.filter(id=account_scope)
    post = None
    if post_id:
        post = _post(ws, post_id)
        _editable(post, request, m)
    initial: dict[str, Any] = {}
    if scheduled_date:
        with contextlib.suppress(ValueError):
            initial["scheduled_date"] = dt.date.fromisoformat(scheduled_date).isoformat()
    if scheduled_time:
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                initial["scheduled_time"] = dt.datetime.strptime(scheduled_time, fmt).strftime("%H:%M")
                break
            except ValueError:
                continue
    template_data = editor.resolve_template_data(template, ws) if template else None
    if template_data:
        initial["template"] = template_data
    if account_scope and post is None:
        initial["selected_accounts"] = [account_scope]
    role = m.workspace_role
    return {
        "workspace": {
            "id": str(ws.id),
            "name": ws.name,
            "timezone": ws.effective_timezone or "UTC",
            "approval_workflow_mode": ws.approval_workflow_mode,
            "default_first_comment": ws.default_first_comment,
            "default_hashtags": list(ws.default_hashtags or []),
        },
        "accounts": [_account(a) for a in accounts.order_by("platform", "account_name")],
        "categories": [
            {"id": str(c.id), "name": c.name, "color": c.color} for c in ContentCategory.objects.for_workspace(ws.id)
        ],
        "tags": list(Tag.objects.for_workspace(ws.id).values_list("name", flat=True)),
        "queues": [
            {
                "id": str(q.id),
                "name": q.name,
                "social_account_id": str(q.social_account_id),
                "account_name": q.social_account.account_name,
                "platform": q.social_account.platform,
            }
            for q in Queue.objects.for_workspace(ws.id).filter(is_active=True).select_related("social_account")
        ],
        "perms": {
            "publish_directly": bool(perms.get("publish_directly")),
            "approve_posts": bool(perms.get("approve_posts")),
            "edit_others_posts": bool(perms.get("edit_others_posts")),
            "view_internal_notes": role not in ("client", "viewer"),
        },
        "unsplash_enabled": unsplash.enabled(),
        "account_scope": account_scope if (post is not None and account_scope) else "",
        "initial": initial,
        "post": _post_detail(post, ws, request.user, perms) if post else None,
    }


class AccountIn(Schema):
    id: uuid.UUID
    title: str | None = None
    caption: str | None = None
    first_comment: str | None = None
    extra: dict[str, Any] | None = None


class SaveIn(Schema):
    action: str = "save_draft"
    title: str = ""
    caption: str = ""
    first_comment: str = ""
    internal_notes: str = ""
    tags: list[str] = []
    category_id: uuid.UUID | None = None
    accounts: list[AccountIn] = []
    account_scope: uuid.UUID | None = None
    media_asset_ids: list[uuid.UUID] | None = None
    scheduled_date: dt.date | None = None
    scheduled_time: dt.time | None = None
    queue_id: uuid.UUID | None = None
    recurring: dict[str, Any] | None = None


def _payload(p: SaveIn) -> editor.EditorPayload:
    return editor.EditorPayload(
        action=p.action,
        title=p.title,
        caption=p.caption,
        first_comment=p.first_comment,
        internal_notes=p.internal_notes,
        tags=p.tags,
        category_id=str(p.category_id) if p.category_id else None,
        accounts=[
            editor.AccountInput(
                id=str(a.id), title=a.title, caption=a.caption, first_comment=a.first_comment, extra=a.extra
            )
            for a in p.accounts
        ],
        account_scope=str(p.account_scope) if p.account_scope else None,
        media_asset_ids=[str(x) for x in p.media_asset_ids] if p.media_asset_ids is not None else None,
        scheduled_date=p.scheduled_date,
        scheduled_time=p.scheduled_time,
        queue_id=str(p.queue_id) if p.queue_id else None,
        recurring=p.recurring,
    )


def _save(request, m, post: Post | None, payload: SaveIn) -> dict:
    try:
        saved = editor.save(post, m.workspace, request.user, _perms(m), _payload(payload))
    except editor.EditorError as exc:
        raise HttpError(400, exc.message) from exc
    except PermissionDenied as exc:
        raise HttpError(403, str(exc)) from exc
    except ValueError as exc:  # approval-gate and similar service errors
        raise HttpError(400, str(exc)) from exc
    return _summary(saved)


@router.post("/{workspace_id}/composer/posts", summary="Create a post (any composer action)")
def create(request, workspace_id: uuid.UUID, payload: SaveIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    return _save(request, m, None, payload)


@router.post("/{workspace_id}/composer/posts/{uuid:post_id}", summary="Save an existing post")
def save(request, workspace_id: uuid.UUID, post_id: uuid.UUID, payload: SaveIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    post = _post(m.workspace, post_id)
    _editable(post, request, m)
    return _save(request, m, post, payload)


@router.get("/{workspace_id}/composer/posts/{uuid:post_id}", summary="Post as the composer sees it")
def detail(request, workspace_id: uuid.UUID, post_id: uuid.UUID):
    m = scoped(request, workspace_id)
    return _post_detail(_post(m.workspace, post_id), m.workspace, request.user, _perms(m))


class TransitionIn(Schema):
    target_status: str


@router.post(
    "/{workspace_id}/composer/posts/{uuid:post_id}/platform-posts/{uuid:pp_id}/transition",
    summary="Move one account's post between statuses",
)
def transition(request, workspace_id: uuid.UUID, post_id: uuid.UUID, pp_id: uuid.UUID, payload: TransitionIn):
    m = scoped(request, workspace_id)
    post = _post(m.workspace, post_id)
    pp = get_object_or_404(post.platform_posts.select_related("post", "social_account"), id=pp_id)
    try:
        editor.transition_child(pp, payload.target_status.strip(), _perms(m))
    except PermissionDenied as exc:
        raise HttpError(403, str(exc)) from exc
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"platform_post_id": str(pp.id), "status": pp.status, "post_status": post.status}


@router.delete("/{workspace_id}/composer/posts/{uuid:post_id}", summary="Delete a post, or one account's row")
def delete(request, workspace_id: uuid.UUID, post_id: uuid.UUID, account: uuid.UUID | None = None):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    post = _post(m.workspace, post_id)
    _editable(post, request, m)
    try:
        editor.delete_post(post, str(account) if account else None)
    except editor.EditorError as exc:
        raise HttpError(400, exc.message) from exc
    return {"deleted": True}


@router.post("/{workspace_id}/composer/posts/{uuid:post_id}/clone", summary="Duplicate as a fresh draft")
def clone(request, workspace_id: uuid.UUID, post_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    new = clone_post(_post(m.workspace, post_id), author=request.user)
    return {"id": str(new.id)}


class TemplateIn(Schema):
    name: str = ""
    description: str = ""


@router.post("/{workspace_id}/composer/posts/{uuid:post_id}/save-as-template", summary="Save as a template")
def save_template(request, workspace_id: uuid.UUID, post_id: uuid.UUID, payload: TemplateIn):
    m = scoped(request, workspace_id)
    tpl = editor.save_as_template(
        _post(m.workspace, post_id), m.workspace, request.user, payload.name, payload.description
    )
    return {"id": str(tpl.id), "name": tpl.name}


# ---------------------------------------------------------------------------
# Platform lookups and stock photos
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/composer/pinterest-boards/{uuid:account_id}", summary="Pinterest boards")
def pinterest_boards(request, workspace_id: uuid.UUID, account_id: uuid.UUID):
    m = scoped(request, workspace_id)
    account = get_object_or_404(SocialAccount, id=account_id, workspace=m.workspace, platform="pinterest")
    try:
        return {"boards": platform_info.pinterest_boards(m.workspace, account)}
    except RuntimeError as exc:
        raise HttpError(502, str(exc)) from exc


@router.get("/{workspace_id}/composer/tiktok-creator-info/{uuid:account_id}", summary="TikTok creator info")
def tiktok_info(request, workspace_id: uuid.UUID, account_id: uuid.UUID):
    m = scoped(request, workspace_id)
    account = get_object_or_404(SocialAccount, id=account_id, workspace=m.workspace, platform="tiktok")
    return platform_info.tiktok_creator_info(m.workspace, account)


@router.get("/{workspace_id}/composer/unsplash", summary="Search Unsplash")
def unsplash_search(request, workspace_id: uuid.UUID, q: str = ""):
    scoped(request, workspace_id)
    try:
        return unsplash.search(q)
    except unsplash.UnsplashError as exc:
        raise HttpError(exc.status, exc.message) from exc


class UnsplashImportIn(Schema):
    photos: list[dict[str, Any]]


@router.post("/{workspace_id}/composer/unsplash/import", summary="Import Unsplash photos into the library")
def unsplash_import(request, workspace_id: uuid.UUID, payload: UnsplashImportIn):
    m = scoped(request, workspace_id)
    require_perm(m, "upload_media")
    try:
        assets, failed = unsplash.import_photos(m.workspace, request.user, payload.photos)
    except unsplash.UnsplashError as exc:
        raise HttpError(exc.status, exc.message) from exc
    return {"assets": [_asset_ref(a) for a in assets], "failed": failed}


# ---------------------------------------------------------------------------
# Templates, categories, tags
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/composer/templates", summary="Built-in and saved templates")
def templates(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    return {
        "categories": TEMPLATE_CATEGORIES,
        "featured_ids": [t["id"] for t in get_featured_templates()],
        "builtin": get_all_templates(),
        "saved": [
            {
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "template_data": t.template_data,
                "created_by": t.created_by.display_name if t.created_by else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in PostTemplate.objects.for_workspace(m.workspace.id).select_related("created_by")
        ],
    }


@router.delete("/{workspace_id}/composer/templates/{uuid:template_id}", summary="Delete a saved template")
def template_delete(request, workspace_id: uuid.UUID, template_id: uuid.UUID):
    m = scoped(request, workspace_id)
    get_object_or_404(PostTemplate, id=template_id, workspace=m.workspace).delete()
    return {"deleted": True}


def _category(c: ContentCategory) -> dict:
    return {"id": str(c.id), "name": c.name, "color": c.color, "position": c.position}


@router.get("/{workspace_id}/composer/categories", summary="Content categories")
def categories(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    return {"categories": [_category(c) for c in ContentCategory.objects.for_workspace(m.workspace.id)]}


class CategoryIn(Schema):
    name: str
    color: str = "#0a0a0a"


def _check_category(payload: CategoryIn) -> None:
    if not payload.name.strip():
        raise HttpError(400, "Name is required.")
    if len(payload.name.strip()) > 100:
        raise HttpError(400, "Name is too long.")
    c = payload.color.strip()
    if len(c) != 7 or not c.startswith("#") or any(ch not in "0123456789abcdefABCDEF" for ch in c[1:]):
        raise HttpError(400, "Colour must be a hex value like #3B82F6.")


@router.post("/{workspace_id}/composer/categories", summary="Create a category")
def category_create(request, workspace_id: uuid.UUID, payload: CategoryIn):
    m = scoped(request, workspace_id)
    _check_category(payload)
    c = ContentCategory.objects.create(
        workspace=m.workspace,
        name=payload.name.strip(),
        color=payload.color.strip(),
        position=editor.next_category_position(m.workspace),
    )
    return _category(c)


@router.patch("/{workspace_id}/composer/categories/{uuid:category_id}", summary="Edit a category")
def category_edit(request, workspace_id: uuid.UUID, category_id: uuid.UUID, payload: CategoryIn):
    m = scoped(request, workspace_id)
    _check_category(payload)
    c = get_object_or_404(ContentCategory, id=category_id, workspace=m.workspace)
    c.name, c.color = payload.name.strip(), payload.color.strip()
    c.save(update_fields=["name", "color", "updated_at"])
    return _category(c)


@router.delete("/{workspace_id}/composer/categories/{uuid:category_id}", summary="Delete a category")
def category_delete(request, workspace_id: uuid.UUID, category_id: uuid.UUID):
    m = scoped(request, workspace_id)
    get_object_or_404(ContentCategory, id=category_id, workspace=m.workspace).delete()
    return {"deleted": True}


@router.get("/{workspace_id}/composer/tags", summary="Workspace tags")
def tags(request, workspace_id: uuid.UUID, q: str = ""):
    m = scoped(request, workspace_id)
    qs = Tag.objects.for_workspace(m.workspace.id)
    if q.strip():
        qs = qs.filter(name__icontains=q.strip())
    return {"tags": [{"id": str(t.id), "name": t.name} for t in qs[:50]]}


class TagIn(Schema):
    name: str


@router.post("/{workspace_id}/composer/tags", summary="Create a tag")
def tag_create(request, workspace_id: uuid.UUID, payload: TagIn):
    m = scoped(request, workspace_id)
    names = parse_and_truncate_tag_string(payload.name)
    if not names:
        raise HttpError(400, "Tag name is required.")
    tag, created = Tag.objects.get_or_create(workspace=m.workspace, name=names[0])
    return {"id": str(tag.id), "name": tag.name, "created": created}


# ---------------------------------------------------------------------------
# Ideas board
# ---------------------------------------------------------------------------


def _idea(i: Idea) -> dict:
    return {
        "id": str(i.id),
        "title": i.title,
        "description": i.description,
        "tags": list(i.tags or []),
        "group_id": str(i.group_id) if i.group_id else None,
        "position": i.position,
        "author": i.author.display_name if i.author else None,
        "post_id": str(i.post_id) if i.post_id else None,
        "media": ideas.idea_media(i),
        "updated_at": i.updated_at.isoformat(),
    }


def _board(workspace, tag=None) -> dict:
    cols, all_tags = ideas.columns(workspace, tag)
    return {
        "columns": [{"id": c["id"], "name": c["label"], "ideas": [_idea(i) for i in c["ideas"]]} for c in cols],
        "tags": all_tags,
        "active_tag": tag or "",
    }


@router.get("/{workspace_id}/composer/ideas", summary="Kanban board")
def board(request, workspace_id: uuid.UUID, tag: str = ""):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    return _board(m.workspace, tag or None)


class IdeaIn(Schema):
    title: str
    description: str = ""
    tags: list[str] = []
    group_id: uuid.UUID | None = None
    media_asset_ids: list[uuid.UUID] = []


@router.post("/{workspace_id}/composer/ideas", summary="Create an idea")
def idea_create(request, workspace_id: uuid.UUID, payload: IdeaIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    ws = m.workspace
    if not payload.title.strip():
        raise HttpError(400, "Title is required.")
    group = (
        IdeaGroup.objects.filter(id=payload.group_id, workspace=ws).first()
        if payload.group_id
        else ideas.ensure_default_groups(ws).first()
    )
    tags_list = parse_and_truncate_tag_string(",".join(payload.tags))
    media_ids = ideas.normalize_media_ids([str(x) for x in payload.media_asset_ids])
    idea = Idea.objects.create(
        workspace=ws,
        author=request.user,
        title=payload.title.strip(),
        description=payload.description.strip(),
        tags=tags_list,
        group=group,
        status=Idea.Status.UNASSIGNED,
        media_asset_id=media_ids[0] if media_ids else None,
    )
    ideas.sync_media(idea, ws, media_ids)
    editor.sync_tags_to_model(ws, tags_list)
    return _idea(ideas.ideas_queryset(ws).get(id=idea.id))


@router.patch("/{workspace_id}/composer/ideas/{uuid:idea_id}", summary="Edit an idea")
def idea_edit(request, workspace_id: uuid.UUID, idea_id: uuid.UUID, payload: IdeaIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    ws = m.workspace
    idea = get_object_or_404(Idea, id=idea_id, workspace=ws)
    if not payload.title.strip():
        raise HttpError(400, "Title is required.")
    idea.title = payload.title.strip()
    idea.description = payload.description.strip()
    idea.tags = parse_and_truncate_tag_string(",".join(payload.tags))
    if payload.group_id:
        group = IdeaGroup.objects.filter(id=payload.group_id, workspace=ws).first()
        if group:
            idea.group = group
    idea.save(update_fields=["title", "description", "tags", "group", "updated_at"])
    ideas.sync_media(idea, ws, [str(x) for x in payload.media_asset_ids])
    editor.sync_tags_to_model(ws, idea.tags)
    return _idea(ideas.ideas_queryset(ws).get(id=idea.id))


@router.delete("/{workspace_id}/composer/ideas/{uuid:idea_id}", summary="Delete an idea")
def idea_delete(request, workspace_id: uuid.UUID, idea_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    get_object_or_404(Idea, id=idea_id, workspace=m.workspace).delete()
    return {"deleted": True}


class MoveIn(Schema):
    group_id: uuid.UUID
    position: int = 0


@router.post("/{workspace_id}/composer/ideas/{uuid:idea_id}/move", summary="Move an idea (drag and drop)")
def idea_move(request, workspace_id: uuid.UUID, idea_id: uuid.UUID, payload: MoveIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    idea = get_object_or_404(Idea, id=idea_id, workspace=m.workspace)
    group = get_object_or_404(IdeaGroup, id=payload.group_id, workspace=m.workspace)
    idea.group = group
    idea.position = max(0, payload.position)
    idea.save(update_fields=["group", "position", "updated_at"])
    return {"ok": True}


@router.post("/{workspace_id}/composer/ideas/{uuid:idea_id}/create-post", summary="Turn an idea into a draft")
def idea_to_post(request, workspace_id: uuid.UUID, idea_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    idea = get_object_or_404(ideas.ideas_queryset(m.workspace), id=idea_id)
    post = ideas.create_post_from_idea(idea, m.workspace, request.user)
    return {"post_id": str(post.id)}


class GroupIn(Schema):
    name: str


@router.post("/{workspace_id}/composer/idea-groups", summary="Add a column")
def group_create(request, workspace_id: uuid.UUID, payload: GroupIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    if not payload.name.strip():
        raise HttpError(400, "Name is required.")
    g = IdeaGroup.objects.create(
        workspace=m.workspace, name=payload.name.strip(), position=ideas.next_group_position(m.workspace)
    )
    return {"id": str(g.id), "name": g.name}


@router.delete("/{workspace_id}/composer/idea-groups/{uuid:group_id}", summary="Delete an empty column")
def group_delete(request, workspace_id: uuid.UUID, group_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    g = get_object_or_404(IdeaGroup, id=group_id, workspace=m.workspace)
    if g.ideas.exists():
        raise HttpError(400, "Column must be empty before deleting.")
    g.delete()
    return {"deleted": True}


class ReorderIn(Schema):
    order: list[uuid.UUID]


@router.post("/{workspace_id}/composer/idea-groups/reorder", summary="Reorder columns")
def group_reorder(request, workspace_id: uuid.UUID, payload: ReorderIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    groups = {str(g.id): g for g in IdeaGroup.objects.for_workspace(m.workspace.id)}
    for position, gid in enumerate(payload.order):
        g = groups.get(str(gid))
        if g and g.position != position:
            g.position = position
            g.save(update_fields=["position"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


def _feed(f: Feed) -> dict:
    return {"id": str(f.id), "name": f.name, "url": f.url, "website_url": f.website_url, "favicon_url": f.favicon_url}


@router.get("/{workspace_id}/composer/feeds", summary="Subscribed feeds and recent entries")
def feed_list(request, workspace_id: uuid.UUID, feed_id: str = "all", offset: int = 0):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    ctx = feeds.events_context(m.workspace, selected_feed_id=feed_id, offset=max(0, offset))
    return {
        "feeds": [_feed(f) for f in ctx["feeds"]],
        "selected_feed_id": ctx["selected_feed_id"],
        "events": [
            {**e, "published_at": e["published_at"].isoformat() if e["published_at"] else None} for e in ctx["events"]
        ],
        "next_offset": ctx["next_offset"],
        "has_more": ctx["has_more"],
        "total": ctx["total_event_count"],
        "last_refreshed_at": ctx["last_refreshed_at"].isoformat() if ctx["last_refreshed_at"] else None,
    }


class FeedIn(Schema):
    rss_url: str
    name: str = ""
    website_url: str = ""
    #: Curated feeds from Explore are trusted and skip the live validation fetch.
    source: str = ""


@router.post("/{workspace_id}/composer/feeds", summary="Subscribe to a feed")
def feed_add(request, workspace_id: uuid.UUID, payload: FeedIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    try:
        f = feeds.add_feed(
            m.workspace,
            request.user,
            payload.rss_url,
            name=payload.name.strip(),
            website_url=payload.website_url.strip(),
            validate=payload.source != "explore",
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return _feed(f)


@router.delete("/{workspace_id}/composer/feeds/{uuid:feed_id}", summary="Unsubscribe")
def feed_delete(request, workspace_id: uuid.UUID, feed_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    feeds.remove_feed(get_object_or_404(Feed, id=feed_id, workspace=m.workspace))
    return {"deleted": True}


@router.get("/{workspace_id}/composer/feeds/explore", summary="Curated feeds by category")
def feed_explore(request, workspace_id: uuid.UUID, category: str = "osir-favorites"):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    return feeds.explore(m.workspace, category)


# ---------------------------------------------------------------------------
# CSV import (state lives in the session, like the Django flow)
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/composer/csv/upload", summary="Upload a CSV and get the column mapping")
def csv_upload(request, workspace_id: uuid.UUID, csv_file: UploadedFile = File(...)):  # noqa: B008
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    try:
        headers, rows = csv_import.parse_upload(csv_file)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    request.session[f"csv_import_{m.workspace.id}"] = {"headers": headers, "rows": rows, "filename": csv_file.name}
    return {
        "headers": headers,
        "preview_rows": rows[:5],
        "total_rows": len(rows),
        "auto_mapping": csv_import.auto_mapping(headers),
        "fields": csv_import.FIELDS,
    }


class MappingIn(Schema):
    mapping: dict[str, int | None]


@router.post("/{workspace_id}/composer/csv/validate", summary="Validate rows with a mapping")
def csv_validate(request, workspace_id: uuid.UUID, payload: MappingIn):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    data = request.session.get(f"csv_import_{m.workspace.id}")
    if not data:
        raise HttpError(400, "No CSV data found. Please upload again.")
    mapping = csv_import.clean_mapping(payload.mapping)
    request.session[f"csv_mapping_{m.workspace.id}"] = mapping
    return csv_import.validate_rows(m.workspace, data["rows"], mapping)


@router.post("/{workspace_id}/composer/csv/confirm", summary="Create the posts")
def csv_confirm(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "create_posts")
    data = request.session.get(f"csv_import_{m.workspace.id}")
    mapping = request.session.get(f"csv_mapping_{m.workspace.id}")
    if not data or not mapping:
        raise HttpError(400, "No CSV data found. Please upload again.")
    result = csv_import.import_rows(m.workspace, request.user, data["rows"], mapping)
    request.session.pop(f"csv_import_{m.workspace.id}", None)
    request.session.pop(f"csv_mapping_{m.workspace.id}", None)
    return result


@router.get("/{workspace_id}/composer/drafts", summary="Posts whose every account is still a draft")
def drafts(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    qs = (
        Post.objects.for_workspace(m.workspace.id)
        .filter(platform_posts__status="draft")
        .exclude(
            platform_posts__status__in=[
                "pending_review",
                "pending_client",
                "approved",
                "scheduled",
                "publishing",
                "published",
            ]
        )
        .distinct()
        .select_related("author")
        .prefetch_related("platform_posts__social_account")
        .order_by("-updated_at")
    )
    return {
        "drafts": [
            {
                "id": str(p.id),
                "title": p.title,
                "caption": p.caption,
                "author": p.author.display_name if p.author else None,
                "proposed_publish_at": p.proposed_publish_at.isoformat() if p.proposed_publish_at else None,
                "platforms": [pp.social_account.platform for pp in p.platform_posts.all()],
                "updated_at": p.updated_at.isoformat(),
            }
            for p in qs
        ]
    }
