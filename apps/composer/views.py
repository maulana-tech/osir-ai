"""Views for the Post Composer (F-2.1)."""

import base64
import contextlib
import json
import re
import uuid
from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import models, transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.common.validators import (
    parse_and_truncate_tag_string,
)
from apps.members.decorators import require_permission
from apps.members.models import WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

from . import csv_import, editor, feeds, ideas, platform_info, unsplash
from .forms import ContentCategoryForm, PostForm
from .models import (
    ContentCategory,
    Feed,
    Idea,
    IdeaGroup,
    PlatformPost,
    Post,
    PostMedia,
    PostTemplate,
    Tag,
)

# Shown when every posting slot within the lookahead horizon is already taken.
_QUEUE_FULL_MSG = "No open posting slot within the scheduling horizon — add posting slots or free one up."


def _get_workspace(request, workspace_id):
    """Resolve workspace and enforce membership check."""
    workspace = get_object_or_404(Workspace, id=workspace_id)
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    has_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        workspace=workspace,
    ).exists()
    if not has_membership:
        raise PermissionDenied("You are not a member of this workspace.")
    return workspace


def _is_valid_uuid(value):
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        return False
    return True


def _parse_selected_account_ids(raw):
    """Split a comma-separated ``selected_accounts`` value into account IDs.

    Non-UUID entries are dropped: they can only come from a crafted or
    corrupted request, and letting them reach a UUIDField lookup raises
    ValidationError (an unhandled 500) instead of being ignored.
    """
    return [s.strip() for s in (raw or "").split(",") if s.strip() and _is_valid_uuid(s.strip())]


def _get_account_scope(request):
    """Return the validated ``account_scope`` POST value, or ``None`` when unscoped.

    The hidden input is server-rendered from a UUID-validated ``?account=``
    param, so a malformed value means a crafted or corrupted request —
    reject it outright (HTTP 400) rather than guessing which rows to touch.
    """
    scope = request.POST.get("account_scope", "").strip()
    if not scope:
        return None
    if not _is_valid_uuid(scope):
        raise SuspiciousOperation("Malformed account_scope.")
    return scope


@login_required
@require_permission("create_posts")
def compose(request, workspace_id, post_id=None):
    """Render the full-page composer for creating or editing a post."""
    workspace = _get_workspace(request, workspace_id)

    # ?account= scopes the composer to one connected account (calendar links).
    # Validate it up front: a malformed value must behave as "unscoped" rather
    # than leak into UUID lookups (ValidationError → 500) or the hidden
    # account_scope input the save endpoints trust.
    account_filter = request.GET.get("account", "").strip()
    if account_filter and not _is_valid_uuid(account_filter):
        account_filter = ""

    # True when the Schedule Post panel is pre-filled from a draft's *proposed*
    # time rather than a committed schedule — the composer uses this to keep the
    # primary action as "Save Draft" instead of arming "schedule for real".
    schedule_prefill_is_proposed = False

    # Load existing post or prepare a blank one
    if post_id:
        post = get_object_or_404(Post, id=post_id, workspace=workspace)
        # Enforce edit permissions: authors can edit their own posts,
        # but editing another user's post requires edit_others_posts.
        membership = request.workspace_membership
        perms = membership.effective_permissions if membership else {}
        if post.author != request.user and not perms.get("edit_others_posts", False):
            raise PermissionDenied("You do not have permission to edit this post.")
        form = PostForm(instance=post)
        # Prefer a committed schedule; fall back to a draft-stage proposal so
        # the Schedule Post panel shows whichever time the post carries.
        prefill_dt = post.scheduled_at or post.proposed_publish_at
        if prefill_dt:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
            local_dt = prefill_dt.astimezone(tz)
            form.initial["scheduled_date"] = local_dt.strftime("%Y-%m-%d")
            form.initial["scheduled_time"] = local_dt.strftime("%H:%M")
            schedule_prefill_is_proposed = post.scheduled_at is None
        # One fetch serves selected ids, extras, and the status checks below.
        platform_post_list = list(post.platform_posts.select_related("social_account"))
        if account_filter:
            selected_account_ids = [
                pp.social_account_id for pp in platform_post_list if str(pp.social_account_id) == account_filter
            ]
        else:
            selected_account_ids = [pp.social_account_id for pp in platform_post_list]
        media_attachments = post.media_attachments.select_related("media_asset").all()
        platform_extras = {str(pp.social_account_id): (pp.platform_extra or {}) for pp in platform_post_list}
        template_data = None
    else:
        post = None
        # Pre-fill scheduled date/time from query params (e.g. when coming from calendar "+" CTA)
        initial = {}
        qs_date = request.GET.get("scheduled_date")
        qs_time = request.GET.get("scheduled_time")
        if qs_date:
            with contextlib.suppress(ValueError):
                initial["scheduled_date"] = datetime.strptime(qs_date, "%Y-%m-%d").date().isoformat()
        if qs_time:
            parsed_time = None
            for fmt in ("%H:%M", "%H:%M:%S"):
                try:
                    parsed_time = datetime.strptime(qs_time, fmt).time()
                    break
                except ValueError:
                    continue
            if parsed_time is not None:
                initial["scheduled_time"] = parsed_time.strftime("%H:%M")
        # Resolve ?template=<id> into template_data (supports both built-in int IDs
        # and PostTemplate UUIDs). Seed caption so it pre-fills the form.
        template_data = editor.resolve_template_data(request.GET.get("template"), workspace)
        if template_data and template_data.get("caption"):
            initial["caption"] = template_data["caption"]
        form = PostForm(initial=initial)
        platform_post_list = []
        selected_account_ids = []
        media_attachments = []
        platform_extras = {}

    # Clear any stale pending media from previous compose sessions.
    # Each compose page load starts fresh; the upload flow re-populates
    # the session as the user adds files.
    from apps.media_library.models import MediaAsset

    session_key = f"pending_media_{workspace.id}"
    request.session.pop(session_key, None)
    pending_assets = MediaAsset.objects.none()

    # Connected social accounts for this workspace
    social_accounts = (
        SocialAccount.objects.for_workspace(workspace.id)
        .filter(
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        )
        .order_by("platform", "account_name")
    )

    # When opening from calendar with a specific account, show only that account.
    if account_filter:
        social_accounts = social_accounts.filter(id=account_filter)
        if not post_id and social_accounts.exists():
            selected_account_ids = [account_filter]

    # Platform character limits for JS
    char_limits = {}
    for acc in social_accounts:
        cfg = dict(acc.field_config)
        cfg["supports_first_comment"] = acc.supports_first_comment()
        char_limits[str(acc.id)] = {
            "platform": acc.platform,
            "limit": acc.char_limit,
            # Each of these costs two characters once the provider escapes it,
            # so the live counter can charge for them as the user types.
            "escaped_chars": acc.escaped_chars,
            "name": acc.account_name or acc.account_handle,
            **cfg,
        }

    # Workspace defaults
    default_first_comment = workspace.default_first_comment
    default_hashtags = workspace.default_hashtags

    # Categories for dropdown
    categories = ContentCategory.objects.for_workspace(workspace.id)

    # Queues for "Add to Queue" action
    from apps.calendar.models import Queue

    queues = (
        Queue.objects.for_workspace(workspace.id).filter(is_active=True).select_related("social_account", "category")
    )

    # Permissions for action buttons
    membership = request.workspace_membership
    perms = membership.effective_permissions if membership else {}
    can_publish = perms.get("publish_directly", False)
    can_approve = perms.get("approve_posts", False)
    ws_role = membership.workspace_role if membership else None
    can_view_internal_notes = ws_role not in ("client", "viewer") if ws_role else True

    # Approval workflow context
    workflow_mode = workspace.approval_workflow_mode
    show_resubmit_button = any(pp.status in ("changes_requested", "rejected", "approved") for pp in platform_post_list)
    # Fresh drafts get "Submit for Approval"; posts already in the workflow
    # (changes-requested / rejected / approved-but-edited) get "Resubmit" instead.
    show_submit_button = workflow_mode != "none" and not show_resubmit_button
    # Once the post is committed to publishing, the Schedule Post panel re-times
    # a live schedule; while still a draft it captures a *proposed* time on save.
    # Mirror _capture_proposed_publish_at's guard exactly (scheduled_at OR a
    # committed child) so the hint, the JS schedule-arming, and the save path
    # never disagree.
    post_is_scheduled = post is not None and (
        post.scheduled_at is not None
        or any(pp.status in ("scheduled", "publishing", "published") for pp in platform_post_list)
    )

    # Approval history and comments for existing posts
    approval_history = []
    post_comments = []
    latest_feedback = None
    if post:
        from apps.approvals.models import ApprovalAction

        # Show recent history (bounded) — a heavily-cycled post can accumulate
        # unboundedly many actions; 50 is plenty for the timeline.
        approval_history = list(
            ApprovalAction.objects.filter(post=post).select_related("user").order_by("-created_at")[:50]
        )
        # Most recent reviewer feedback to surface in the edit banner.
        latest_feedback = next(
            (a for a in approval_history if a.action in ("changes_requested", "rejected") and a.comment),
            None,
        )
        from apps.approvals.comments import get_comments_for_post

        post_comments = get_comments_for_post(post, request.user)

    # Workspace tags for the tag dropdown
    all_tags = Tag.objects.for_workspace(workspace.id)

    # Failed platform posts with an error message — shown as a banner so the
    # user can see why a publish failed before retrying.
    failed_platform_posts = [
        pp for pp in platform_post_list if pp.status == PlatformPost.Status.FAILED and pp.publish_error
    ]

    # A first comment that failed leaves the post itself published, so it never
    # shows up in the banner above — without this the post looks fully
    # successful while the comment is silently missing.
    failed_first_comments = [
        pp for pp in platform_post_list if pp.first_comment_status == PlatformPost.FirstCommentStatus.FAILED
    ]

    # Build media_items for the initial preview render
    media_items = []
    for att in media_attachments:
        asset = att.media_asset
        media_items.append(
            {
                "url": asset.file.url if asset.file else "",
                "is_video": asset.is_video,
                "filename": asset.filename,
            }
        )
    if not media_items:
        for asset in pending_assets:
            media_items.append(
                {
                    "url": asset.file.url if asset.file else "",
                    "is_video": asset.is_video,
                    "filename": asset.filename,
                }
            )

    # Resolve thumbnail/cover image URLs for per-account assets already saved
    thumb_ids = [
        extra.get("thumbnail_asset_id") for extra in platform_extras.values() if extra.get("thumbnail_asset_id")
    ]
    cover_ids = [
        extra.get("cover_image_asset_id") for extra in platform_extras.values() if extra.get("cover_image_asset_id")
    ]
    all_asset_ids = [aid for aid in thumb_ids + cover_ids if aid]
    asset_url_map = {}
    if all_asset_ids:
        for asset in MediaAsset.objects.filter(id__in=all_asset_ids, workspace=workspace):
            url = ""
            if asset.thumbnail:
                url = asset.thumbnail.url
            elif asset.file:
                url = asset.file.url
            asset_url_map[str(asset.id)] = url
    for _acc_id, extra in platform_extras.items():
        tid = extra.get("thumbnail_asset_id")
        if tid and tid in asset_url_map:
            extra["thumbnail_url"] = asset_url_map[tid]
        cid = extra.get("cover_image_asset_id")
        if cid and cid in asset_url_map:
            extra["cover_image_url"] = asset_url_map[cid]

    context = {
        "workspace": workspace,
        "post": post,
        "form": form,
        "social_accounts": social_accounts,
        "selected_account_ids": [str(aid) for aid in selected_account_ids],
        "platform_extras": platform_extras,
        "media_attachments": media_attachments,
        "media_items": media_items,
        "char_limits": char_limits,
        "default_first_comment": default_first_comment,
        "default_hashtags": json.dumps(default_hashtags),
        "can_publish": can_publish,
        "can_approve": can_approve,
        "can_view_internal_notes": can_view_internal_notes,
        "is_edit": post is not None,
        "schedule_prefill_is_proposed": schedule_prefill_is_proposed,
        "post_is_scheduled": post_is_scheduled,
        "categories": categories,
        "queues": queues,
        "template_data_json": json.dumps(template_data) if template_data else "null",
        "workflow_mode": workflow_mode,
        "show_submit_button": show_submit_button,
        "show_resubmit_button": show_resubmit_button,
        "approval_history": approval_history,
        "latest_feedback": latest_feedback,
        "post_comments": post_comments,
        "pending_assets": pending_assets,
        "all_tags": all_tags,
        # When opened scoped to one account (?account=), the form only renders
        # that account — the save endpoints use this to leave siblings alone.
        "account_scope": account_filter if (post_id and account_filter) else "",
        "failed_platform_posts": failed_platform_posts,
        "failed_first_comments": failed_first_comments,
        "unsplash_enabled": bool(settings.UNSPLASH_ACCESS_KEY),
    }
    return render(request, "composer/compose.html", context)


def _payload_from_form(request, form):
    """Build the shared editor payload from the composer's form POST."""
    data = request.POST
    accounts = []
    for acc_id in _parse_selected_account_ids(data.get("selected_accounts", "")):
        account = SocialAccount.objects.filter(id=acc_id).only("platform").first()
        platform = account.platform if account else ""
        extra = None
        if platform == "youtube":
            extra = {
                "tags": data.get(f"yt_tags_{acc_id}", ""),
                "privacy_status": data.get(f"yt_privacy_status_{acc_id}", "public"),
                "made_for_kids": data.get(f"yt_made_for_kids_{acc_id}"),
                "thumbnail_asset_id": data.get(f"yt_thumbnail_asset_id_{acc_id}", ""),
            }
        elif platform == "pinterest":
            extra = {
                "board_id": data.get(f"pin_board_id_{acc_id}", ""),
                "link_url": data.get(f"pin_link_url_{acc_id}", ""),
                "alt_text": data.get(f"pin_alt_text_{acc_id}", ""),
                "tag_products": data.get(f"pin_tag_products_{acc_id}", ""),
                "allow_comments": data.get(f"pin_allow_comments_{acc_id}"),
                "show_similar_products": data.get(f"pin_show_similar_{acc_id}"),
                "cover_image_asset_id": data.get(f"pin_cover_image_asset_id_{acc_id}", ""),
            }
        elif platform == "tiktok" and f"tiktok_privacy_level_{acc_id}" in data:
            # Only rebuild extras when the TikTok panel was part of the form,
            # so non-composer saves can't wipe a previously chosen privacy level.
            extra = {
                "privacy_level": data.get(f"tiktok_privacy_level_{acc_id}", ""),
                "allow_comment": data.get(f"tiktok_allow_comment_{acc_id}"),
                "allow_duet": data.get(f"tiktok_allow_duet_{acc_id}"),
                "allow_stitch": data.get(f"tiktok_allow_stitch_{acc_id}"),
                "brand_organic": data.get(f"tiktok_brand_organic_{acc_id}"),
                "brand_content": data.get(f"tiktok_brand_content_{acc_id}"),
                "is_aigc": data.get(f"tiktok_is_aigc_{acc_id}"),
                "video_cover_timestamp_ms": data.get(f"tiktok_video_cover_timestamp_ms_{acc_id}", ""),
            }
        accounts.append(
            editor.AccountInput(
                id=acc_id,
                title=data.get(f"override_title_{acc_id}", ""),
                caption=data.get(f"override_caption_{acc_id}", ""),
                first_comment=data.get(f"override_comment_{acc_id}", ""),
                extra=extra,
            )
        )
    cd = form.cleaned_data
    recurring = None
    if data.get("make_recurring"):
        recurring = {
            "frequency": data.get("recurrence_frequency", "weekly"),
            "interval": data.get("recurrence_interval", "1"),
            "end_date": data.get("recurrence_end_date", ""),
        }
    return editor.EditorPayload(
        action=data.get("action", "save_draft"),
        title=cd.get("title") or "",
        caption=cd.get("caption") or "",
        first_comment=cd.get("first_comment") or "",
        internal_notes=cd.get("internal_notes") or "",
        tags=cd.get("tags") or [],
        category_id=str(cd["category"].id) if cd.get("category") else None,
        accounts=accounts,
        account_scope=_get_account_scope(request),
        media_asset_ids=None,
        scheduled_date=cd.get("scheduled_date"),
        scheduled_time=cd.get("scheduled_time"),
        queue_id=data.get("queue_id") or None,
        recurring=recurring,
    )


def _pop_pending_media(request, workspace):
    """Media queued in the session while composing a new post."""
    session_key = f"pending_media_{workspace.id}"
    pending_ids = request.session.get(session_key, [])
    if pending_ids:
        del request.session[session_key]
    return pending_ids


def _saved_response(request, workspace, post):
    if request.htmx:
        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": json.dumps({"postSaved": {"postId": str(post.id), "status": post.status}}),
                "X-Platform-Statuses": json.dumps(editor.platform_status_map(post)),
            },
        )
    return redirect("composer:compose_edit", workspace_id=workspace.id, post_id=post.id)


@login_required
@require_permission("create_posts")
@require_POST
def save_post(request, workspace_id, post_id=None):
    """Save or update a post (draft, schedule, queue, approval or publish action)."""
    workspace = _get_workspace(request, workspace_id)
    membership = request.workspace_membership
    perms = membership.effective_permissions if membership else {}

    post = None
    orig_content = None
    if post_id:
        post = get_object_or_404(Post, id=post_id, workspace=workspace)
        editor.check_can_edit(post, request.user, perms)
        orig_content = editor.base_content_snapshot(post)  # before the form mutates the instance
        form = PostForm(request.POST, instance=post)
    else:
        form = PostForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    payload = _payload_from_form(request, form)
    if post is None:
        # A new post adopts whatever the media picker queued in the session.
        payload.media_asset_ids = _pop_pending_media(request, workspace)
    try:
        post = editor.save(post, workspace, request.user, perms, payload, orig_content=orig_content)
    except editor.EditorError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    return _saved_response(request, workspace, post)


@login_required
@require_POST
def transition_platform_post(request, workspace_id, post_id, platform_post_id):
    """Move a single PlatformPost (the composer's per-account chip menu)."""
    workspace = _get_workspace(request, workspace_id)
    pp = get_object_or_404(
        PlatformPost.objects.select_related("post", "social_account"),
        id=platform_post_id,
        post_id=post_id,
        post__workspace=workspace,
    )
    target = (request.POST.get("target_status") or "").strip()
    if not target:
        return JsonResponse({"error": "target_status required"}, status=400)
    membership = request.workspace_membership
    perms = membership.effective_permissions if membership else {}
    if pp.status == target:
        return JsonResponse({"ok": True, "status": pp.status, "noop": True})
    try:
        editor.transition_child(pp, target, perms)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "status": pp.status, "platform_post_id": str(pp.id)})


@login_required
@require_permission("create_posts")
@require_POST
def autosave(request, workspace_id, post_id=None):
    """Auto-save every 30 seconds; the first save of a new post creates the draft."""
    workspace = _get_workspace(request, workspace_id)
    membership = request.workspace_membership
    perms = membership.effective_permissions if membership else {}

    post = None
    if post_id:
        post = get_object_or_404(Post, id=post_id, workspace=workspace)
        editor.check_can_edit(post, request.user, perms)
    else:
        client_post_id = request.POST.get("_autosave_post_id", "").strip()
        if client_post_id:
            post = Post.objects.filter(id=client_post_id, workspace=workspace).first()
    is_new = post is None

    data = request.POST
    payload = editor.EditorPayload(
        action="autosave",
        title=data.get("title", ""),
        caption=data.get("caption", ""),
        first_comment=data.get("first_comment", ""),
        internal_notes=data.get("internal_notes", ""),
        tags=parse_and_truncate_tag_string(data.get("tags", "")),
        accounts=[editor.AccountInput(id=a) for a in _parse_selected_account_ids(data.get("selected_accounts", ""))],
        account_scope=_get_account_scope(request),
        media_asset_ids=_pop_pending_media(request, workspace) if is_new else None,
    )
    post = editor.save(post, workspace, request.user, perms, payload)
    return HttpResponse(
        f'<span class="text-xs text-gray-400">Saved {timezone.now().strftime("%H:%M")}</span>',
        headers={"HX-Trigger": json.dumps({"autosaved": {"postId": str(post.id), "isNew": is_new}})},
    )


@login_required
@require_POST
def preview(request, workspace_id):
    """Live preview endpoint - renders platform-specific preview from form state.

    Called via HTMX with debounced POST from the composer.
    Stateless - no DB queries except social account lookup.
    """
    workspace = _get_workspace(request, workspace_id)
    title = request.POST.get("title", "")
    caption = request.POST.get("caption", "")
    first_comment = request.POST.get("first_comment", "")
    selected_ids = _parse_selected_account_ids(request.POST.get("selected_accounts", ""))

    # Build preview data per platform
    previews = []
    if selected_ids:
        accounts = SocialAccount.objects.filter(
            id__in=selected_ids,
            workspace=workspace,
        ).order_by("platform")
        for account in accounts:
            override_title_key = f"override_title_{account.id}"
            override_key = f"override_caption_{account.id}"
            effective_title = request.POST.get(override_title_key, "") or title
            effective_caption = request.POST.get(override_key, "") or caption
            char_limit = account.char_limit
            # Counted after escaping, so the badge matches what gets published.
            char_count = account.caption_wire_length(effective_caption)
            field_config = account.field_config
            previews.append(
                {
                    "account": account,
                    "title": effective_title,
                    "caption": effective_caption,
                    "first_comment": first_comment,
                    "char_count": char_count,
                    "char_limit": char_limit,
                    "is_over_limit": char_count > char_limit,
                    "truncated_caption": effective_caption[:char_limit]
                    if len(effective_caption) > char_limit
                    else effective_caption,
                    "needs_title": field_config["needs_title"],
                }
            )

    # Gather media for preview - check pending session media or post attachments
    from apps.media_library.models import MediaAsset

    media_items = []
    post_id_str = request.POST.get("_autosave_post_id", "")

    if post_id_str:
        try:
            post_obj = Post.objects.get(id=post_id_str, workspace=workspace)
            for att in post_obj.media_attachments.select_related("media_asset").all():
                asset = att.media_asset
                media_items.append(
                    {
                        "url": asset.file.url if asset.file else "",
                        "is_video": asset.is_video,
                        "filename": asset.filename,
                    }
                )
        except Post.DoesNotExist:
            pass

    if not media_items:
        # Check session pending media
        session_key = f"pending_media_{workspace.id}"
        pending_ids = request.session.get(session_key, [])
        if pending_ids:
            for asset in MediaAsset.objects.filter(id__in=pending_ids, workspace=workspace):
                media_items.append(
                    {
                        "url": asset.file.url if asset.file else "",
                        "is_video": asset.is_video,
                        "filename": asset.filename,
                    }
                )

    return render(
        request,
        "composer/partials/preview_panel.html",
        {
            "previews": previews,
            "workspace": workspace,
            "media_items": media_items,
        },
    )


@login_required
@require_GET
def media_picker(request, workspace_id, post_id=None):
    """Modal picker for selecting media from the library."""
    workspace = _get_workspace(request, workspace_id)
    from apps.media_library.models import MediaAsset

    post = None
    if post_id:
        post = get_object_or_404(Post, id=post_id, workspace=workspace)

    assets = MediaAsset.objects.for_workspace_with_shared(workspace.id, workspace.organization_id).order_by(
        "-created_at"
    )[:50]
    return render(
        request,
        "composer/partials/media_picker.html",
        {
            "assets": assets,
            "workspace": workspace,
            "post": post,
        },
    )


@login_required
@require_GET
def thumbnail_picker(request, workspace_id):
    """Modal picker for selecting an image asset as a YouTube thumbnail.

    Image-only, selection dispatches a client-side event; does not attach
    anything server-side.
    """
    workspace = _get_workspace(request, workspace_id)
    from apps.media_library.models import MediaAsset

    assets = (
        MediaAsset.objects.for_workspace(workspace.id)
        .filter(media_type=MediaAsset.MediaType.IMAGE)
        .order_by("-created_at")[:50]
    )
    return render(
        request,
        "composer/partials/thumbnail_picker.html",
        {"assets": assets, "workspace": workspace},
    )


@login_required
@require_POST
def thumbnail_upload(request, workspace_id):
    """Upload an image from the local machine to the media library and return
    its id + URL so the composer can wire it as a YouTube thumbnail.

    Image-only. Returns JSON with asset_id, url, filename.
    """
    workspace = _get_workspace(request, workspace_id)
    uploaded_file = request.FILES.get("file")

    if not uploaded_file:
        return JsonResponse({"error": "No file provided"}, status=400)

    content_type = uploaded_file.content_type or ""
    if not content_type.startswith("image/"):
        return JsonResponse({"error": "Only image files are allowed"}, status=400)

    from apps.media_library.models import MediaAsset

    asset = MediaAsset.objects.create(
        organization=workspace.organization,
        workspace=workspace,
        uploaded_by=request.user,
        file=uploaded_file,
        filename=uploaded_file.name,
        media_type=MediaAsset.MediaType.IMAGE,
        mime_type=content_type,
        file_size=uploaded_file.size,
        source="upload",
    )

    url = ""
    if asset.thumbnail:
        url = asset.thumbnail.url
    elif asset.file:
        url = asset.file.url

    return JsonResponse(
        {
            "asset_id": str(asset.id),
            "url": url,
            "filename": asset.filename,
        }
    )


_RANGE_HEADER_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class _RangeFileIterator:
    """Iterate a bounded byte window of an already-positioned file handle."""

    def __init__(self, file_handle, remaining, chunk_size=64 * 1024):
        self.file_handle = file_handle
        self.remaining = remaining
        self.chunk_size = chunk_size

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining <= 0:
            raise StopIteration
        data = self.file_handle.read(min(self.chunk_size, self.remaining))
        if not data:
            raise StopIteration
        self.remaining -= len(data)
        return data

    def close(self):
        if hasattr(self.file_handle, "close"):
            self.file_handle.close()


@login_required
@require_GET
def media_stream(request, workspace_id, asset_id):
    """Stream a media asset through the app's own origin, with Range support.

    The composer's frame picker draws video frames onto a canvas, which the
    browser only allows for same-origin (or CORS-approved) media. Object
    storage like S3/R2 serves signed URLs from another origin, usually
    without CORS headers, so the raw file URL would taint the canvas.

    Byte-range requests matter here: without them the browser can't seek a
    <video> beyond what it has buffered (the scrubber and filmstrip clicks
    silently do nothing) and has to download the whole file up front.
    """
    workspace = _get_workspace(request, workspace_id)

    from apps.media_library.models import MediaAsset

    asset = get_object_or_404(
        MediaAsset.objects.for_workspace_with_shared(
            workspace_id=workspace.id,
            organization_id=workspace.organization_id,
        ),
        pk=asset_id,
    )
    if not asset.file:
        raise Http404
    # The DB row can outlive the stored object (lifecycle rule, manual S3
    # deletion); opening/stat-ing it then raises a backend error rather than
    # returning an empty FieldFile, so map that to 404 instead of a 500.
    try:
        size = asset.file.size
        file_handle = asset.file.open("rb")
    except Exception:  # noqa: BLE001 - storage backends raise varied errors (OSError, botocore ClientError)
        raise Http404 from None

    content_type = asset.mime_type or "application/octet-stream"
    range_match = _RANGE_HEADER_RE.match(request.headers.get("Range", ""))

    if range_match and size:
        start_str, end_str = range_match.groups()
        if not start_str:
            # Suffix range: the last N bytes.
            length = min(int(end_str or 0), size)
            start = size - length
            end = size - 1
        else:
            start = int(start_str)
            end = min(int(end_str), size - 1) if end_str else size - 1
        if start >= size or start > end:
            file_handle.close()
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        file_handle.seek(start)
        response = StreamingHttpResponse(
            _RangeFileIterator(file_handle, end - start + 1),
            status=206,
            content_type=content_type,
        )
        response["Content-Length"] = str(end - start + 1)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    else:
        response = FileResponse(file_handle, content_type=content_type)

    response["Accept-Ranges"] = "bytes"
    # Asset files are immutable per id - let the browser cache the stream so
    # reopening the frame picker doesn't re-download the whole video.
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
@require_GET
def media_filmstrip(request, workspace_id, asset_id):
    """Return evenly-spaced thumbnail frames for the frame-picker filmstrip.

    Extracted server-side with ffmpeg, which seeks each frame via byte ranges
    instead of making the browser download (and decode) most of the video to
    build the strip client-side.
    """
    workspace = _get_workspace(request, workspace_id)

    import os
    import tempfile

    from apps.media_library.models import MediaAsset
    from apps.media_library.services import extract_video_frames, extract_video_metadata

    asset = get_object_or_404(
        MediaAsset.objects.for_workspace_with_shared(
            workspace_id=workspace.id,
            organization_id=workspace.organization_id,
        ),
        pk=asset_id,
    )
    if asset.media_type != MediaAsset.MediaType.VIDEO or not asset.file:
        raise Http404

    # Mirror media_library's video pipeline: pull the file to one local temp
    # file, then run all the ffmpeg seeks against it. Extracting each frame
    # straight from the (remote) signed URL re-opens the connection and
    # re-reads the moov atom every time - on R2 that was ~1.5s per frame.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{asset.file_extension}", delete=False) as tmp:
            for chunk in asset.file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
    except Exception:  # noqa: BLE001 - storage backends raise varied errors when the object is gone
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise Http404 from None

    try:
        duration = asset.duration or extract_video_metadata(tmp_path).get("duration_seconds") or 0
        if not duration:
            return JsonResponse({"error": "Could not read video duration."}, status=502)

        count = 8
        timestamps = [round(duration * (i + 0.5) / count, 3) for i in range(count)]
        jpegs = extract_video_frames(tmp_path, timestamps, width=160)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    frames = [
        {"time": t, "dataUrl": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}
        for t, jpg in zip(timestamps, jpegs, strict=False)
        if jpg
    ]
    if not frames:
        return JsonResponse({"error": "Could not extract frames."}, status=502)
    return JsonResponse({"frames": frames, "duration": duration})


@login_required
@require_POST
def attach_media(request, workspace_id, post_id):
    """Attach a media asset to a post."""
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)
    media_asset_id = request.POST.get("media_asset_id")

    if not media_asset_id:
        return JsonResponse({"error": "media_asset_id required"}, status=400)

    from apps.media_library.models import MediaAsset

    asset = get_object_or_404(
        MediaAsset.objects.for_workspace_with_shared(workspace.id, workspace.organization_id),
        id=media_asset_id,
    )

    max_pos = post.media_attachments.aggregate(models.Max("position"))["position__max"]
    position = (max_pos or 0) + 1

    attachment, _ = PostMedia.objects.get_or_create(
        post=post,
        media_asset=asset,
        defaults={"position": position},
    )

    # Option A: changing media on an approved post sends it back for re-approval.
    editor.revert_approved_to_review(post)

    response = render(
        request,
        "composer/partials/media_list.html",
        {
            "media_attachments": [attachment],
            "post": post,
            "workspace": workspace,
        },
    )
    response["HX-Trigger"] = "previewUpdate"
    return response


@login_required
@require_POST
def attach_pending_media(request, workspace_id):
    """Attach a library media asset as pending (before post is saved)."""
    workspace = _get_workspace(request, workspace_id)
    media_asset_id = request.POST.get("media_asset_id")

    if not media_asset_id:
        return JsonResponse({"error": "media_asset_id required"}, status=400)

    from apps.media_library.models import MediaAsset

    asset = get_object_or_404(
        MediaAsset.objects.for_workspace_with_shared(workspace.id, workspace.organization_id),
        id=media_asset_id,
    )

    session_key = f"pending_media_{workspace.id}"
    pending = request.session.get(session_key, [])
    asset_id_str = str(asset.id)
    if asset_id_str not in pending:
        pending.append(asset_id_str)
        request.session[session_key] = pending

    response = render(
        request,
        "composer/partials/media_list_pending.html",
        {
            "pending_assets": [asset],
            "workspace": workspace,
        },
    )
    response["HX-Trigger"] = "previewUpdate"
    return response


def _attach_asset_for_composer(request, workspace, asset, post=None):
    """Attach an asset to a post, or queue it in the pending-media session.

    Post path: migrates any session-pending media first (can happen when the
    media picker still uses attach_pending_media after autosave created the
    post and updated the upload URL), then appends the asset at the next
    position. Returns the PostMedia attachment, or None on the pending path.
    """
    from apps.media_library.models import MediaAsset

    session_key = f"pending_media_{workspace.id}"

    if post is not None:
        pending_ids = request.session.get(session_key, [])
        if pending_ids:
            existing_pos = post.media_attachments.aggregate(models.Max("position"))["position__max"] or 0
            for idx, pid in enumerate(pending_ids):
                try:
                    pending_asset = MediaAsset.objects.get(id=pid, workspace=workspace)
                    PostMedia.objects.get_or_create(
                        post=post,
                        media_asset=pending_asset,
                        defaults={"position": existing_pos + idx + 1},
                    )
                except MediaAsset.DoesNotExist:
                    continue
            del request.session[session_key]

        max_pos = post.media_attachments.aggregate(models.Max("position"))["position__max"]
        position = (max_pos or 0) + 1
        return PostMedia.objects.create(post=post, media_asset=asset, position=position)

    # No post yet - store pending media IDs in session so they can be
    # attached when the post is eventually saved.
    pending = request.session.get(session_key, [])
    pending.append(str(asset.id))
    request.session[session_key] = pending
    return None


@login_required
@require_POST
def upload_media(request, workspace_id, post_id=None):
    """Upload a file directly from the composer and optionally attach to a post."""
    workspace = _get_workspace(request, workspace_id)
    uploaded_file = request.FILES.get("file")

    if not uploaded_file:
        return JsonResponse({"error": "No file provided"}, status=400)

    from apps.media_library.models import MediaAsset

    # Determine media type
    content_type = uploaded_file.content_type or ""
    if content_type.startswith("image/"):
        media_type = MediaAsset.MediaType.IMAGE
    elif content_type.startswith("video/"):
        media_type = MediaAsset.MediaType.VIDEO
    elif content_type == "image/gif":
        media_type = MediaAsset.MediaType.GIF
    else:
        media_type = MediaAsset.MediaType.DOCUMENT

    asset = MediaAsset.objects.create(
        organization=workspace.organization,
        workspace=workspace,
        uploaded_by=request.user,
        file=uploaded_file,
        filename=uploaded_file.name,
        media_type=media_type,
        mime_type=content_type,
        file_size=uploaded_file.size,
        source="upload",
    )

    if post_id:
        post = get_object_or_404(Post, id=post_id, workspace=workspace)
        attachment = _attach_asset_for_composer(request, workspace, asset, post)
        # Option A: changing media on an approved post sends it back for re-approval.
        editor.revert_approved_to_review(post)
        response = render(
            request,
            "composer/partials/media_list.html",
            {
                "media_attachments": [attachment],
                "post": post,
                "workspace": workspace,
            },
        )
    else:
        _attach_asset_for_composer(request, workspace, asset)
        response = render(
            request,
            "composer/partials/media_list_pending.html",
            {
                "pending_assets": [asset],
                "workspace": workspace,
            },
        )

    response["X-Uploaded-Asset-Id"] = str(asset.id)
    response["X-Uploaded-Asset-Url"] = asset.file.url
    return response


@login_required
@require_POST
def remove_media(request, workspace_id, post_id, media_id):
    """Remove a media attachment from a post."""
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)
    PostMedia.objects.filter(id=media_id, post=post).delete()

    # Option A: changing media on an approved post sends it back for re-approval.
    editor.revert_approved_to_review(post)

    response = render(
        request,
        "composer/partials/media_list.html",
        {
            "media_attachments": post.media_attachments.select_related("media_asset").all(),
            "post": post,
            "workspace": workspace,
        },
    )
    response["HX-Trigger"] = "previewUpdate"
    return response


@login_required
@require_POST
def remove_pending_media(request, workspace_id, asset_id):
    """Remove a pending media asset (before post is saved)."""
    workspace = _get_workspace(request, workspace_id)

    from apps.media_library.models import MediaAsset
    from apps.media_library.services import delete_asset

    session_key = f"pending_media_{workspace.id}"
    pending = request.session.get(session_key, [])
    asset_id_str = str(asset_id)
    if asset_id_str in pending:
        pending.remove(asset_id_str)
        request.session[session_key] = pending

    # Delete the asset and its files from storage (R2)
    asset = MediaAsset.objects.filter(id=asset_id, workspace=workspace).first()
    if asset:
        with contextlib.suppress(Exception):
            delete_asset(asset)

    # Return updated pending list
    pending_assets = MediaAsset.objects.filter(id__in=pending, workspace=workspace)
    response = render(
        request,
        "composer/partials/media_list_pending.html",
        {
            "pending_assets": pending_assets,
            "workspace": workspace,
        },
    )
    response["HX-Trigger"] = "previewUpdate"
    return response


@login_required
@require_GET
def drafts_list(request, workspace_id):
    """List all drafts for this workspace."""
    workspace = _get_workspace(request, workspace_id)
    # A post is a "draft" when at least one of its PlatformPost children is in
    # the draft state and none have moved into a more advanced workflow stage.
    # Easiest correct query: any post whose only child statuses are "draft".
    drafts = (
        Post.objects.for_workspace(workspace.id)
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

    return render(
        request,
        "composer/drafts_list.html",
        {
            "workspace": workspace,
            "drafts": drafts,
        },
    )


@login_required
@require_POST
def post_delete(request, workspace_id, post_id):
    """Delete a post or a single platform post via HTMX.

    When an ``account`` query parameter is provided, only the PlatformPost for
    that social account is removed.  If it was the last PlatformPost the parent
    Post is deleted as well.  Without the parameter the entire Post (and all
    its PlatformPosts) is deleted.
    """
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)

    account_id = request.GET.get("account") or request.POST.get("account")
    if account_id:
        pp = get_object_or_404(PlatformPost, post=post, social_account_id=account_id)
        pp.delete()
        # If no platform posts remain, clean up the parent post too.
        if not post.platform_posts.exists():
            post.delete()
    else:
        post.delete()

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "postChanged"},
    )


@login_required
@require_POST
def clone_post_view(request, workspace_id, post_id):
    """Clone a post into a fresh draft (Clone / Repost) and open the copy.

    The composer makes published/publishing posts read-only; this is the escape
    hatch to repost — the duplicate starts as a draft with the same content but
    no schedule, so it can be edited and re-queued without touching the original.
    """
    from django.urls import reverse

    from apps.composer.services import clone_post

    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)

    membership = request.workspace_membership
    perms = membership.effective_permissions if membership else {}
    if not perms.get("create_posts", False):
        raise PermissionDenied("You do not have permission to create posts.")

    new_post = clone_post(post, author=request.user)
    target = reverse("composer:compose_edit", kwargs={"workspace_id": workspace.id, "post_id": new_post.id})
    if request.htmx:
        return HttpResponse(status=204, headers={"HX-Redirect": target})
    return redirect(target)


# ---------------------------------------------------------------------------
# Create landing page & Idea CRUD
# ---------------------------------------------------------------------------


def _render_idea_card_fragment(request, idea):
    """Render a single Kanban idea card fragment."""
    _prepare_idea_for_kanban(idea)
    return render_to_string(
        "composer/partials/idea_card.html",
        {
            "idea": idea,
            "group_id": str(idea.group_id) if idea.group_id else "",
        },
        request=request,
    )


def _render_kanban_column_fragment(request, group):
    """Render a single Kanban column fragment."""
    return render_to_string(
        "composer/partials/kanban_column.html",
        {
            "col": {
                "id": str(group.id),
                "key": str(group.id),
                "label": group.name,
                "ideas": [],
            },
        },
        request=request,
    )


def _wants_json_response(request):
    """Detect whether mutation endpoint should return JSON payload."""
    accept = request.headers.get("Accept", "")
    return "application/json" in accept.lower()


@login_required
@require_permission("create_posts")
def create_landing(request, workspace_id):
    """Render the Create landing page with Ideas Kanban board."""
    from apps.composer.builtin_templates import (
        CATEGORIES,
        get_all_templates,
        get_featured_templates,
    )

    workspace = _get_workspace(request, workspace_id)
    tab = request.GET.get("tab", "ideas")
    tag = request.GET.get("tag")

    columns, all_tags = _idea_columns(workspace, tag)

    feeds = Feed.objects.for_workspace(workspace.id)

    context = {
        "workspace": workspace,
        "tab": tab,
        "columns": columns,
        "all_tags": all_tags,
        "active_tag": tag,
        "featured_templates": get_featured_templates(),
        "builtin_templates": get_all_templates(),
        "template_categories": CATEGORIES,
        "feeds": feeds,
    }
    return render(request, "composer/create_landing.html", context)


@login_required
@require_permission("create_posts")
@require_POST
def idea_create(request, workspace_id):
    """Create a new idea via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    tags = parse_and_truncate_tag_string(request.POST.get("tags", ""))

    if not title:
        return HttpResponse("Title is required.", status=400)

    # Assign to the specified group or default to the first group
    group_id = request.POST.get("group")
    if group_id:
        group = IdeaGroup.objects.filter(id=group_id, workspace=workspace).first()
    else:
        group = IdeaGroup.objects.for_workspace(workspace.id).order_by("position").first()

    has_multi_media_payload = "media_asset_ids" in request.POST
    media_asset_ids = _normalize_media_asset_ids(request.POST.get("media_asset_ids", ""))

    # Handle media: pre-uploaded IDs (preferred), direct multipart upload fallback,
    # or legacy single pre-uploaded asset id.
    uploaded_file = request.FILES.get("media") or request.FILES.get("file")
    media_asset_id = request.POST.get("media_asset_id", "").strip()
    if uploaded_file:
        uploaded_asset = _create_idea_media_asset(workspace, request.user, uploaded_file)
        media_asset_ids.append(str(uploaded_asset.id))
    elif not media_asset_ids and media_asset_id:
        from apps.media_library.models import MediaAsset

        legacy_asset = MediaAsset.objects.filter(id=media_asset_id, workspace=workspace).first()
        if legacy_asset:
            media_asset_ids.append(str(legacy_asset.id))

    media_asset_ids = _normalize_media_asset_ids(media_asset_ids)

    with transaction.atomic():
        idea = Idea.objects.create(
            workspace=workspace,
            author=request.user,
            title=title,
            description=description,
            tags=tags,
            group=group,
            status=Idea.Status.UNASSIGNED,
            media_asset_id=media_asset_ids[0] if media_asset_ids else None,
        )

        if has_multi_media_payload or media_asset_ids:
            _sync_idea_media_attachments(idea, workspace, media_asset_ids)

    # Sync any new tags to the Tag model
    editor.sync_tags_to_model(workspace, tags)

    if _wants_json_response(request):
        idea = (
            Idea.objects.for_workspace(workspace.id)
            .select_related("media_asset")
            .prefetch_related("media_attachments__media_asset")
            .get(id=idea.id)
        )
        return JsonResponse(
            {
                "ok": True,
                "idea_id": str(idea.id),
                "group_id": str(idea.group_id) if idea.group_id else "",
                "tags": idea.tags or [],
                "card_html": _render_idea_card_fragment(request, idea),
            }
        )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "ideaChanged"},
    )


@login_required
@require_permission("create_posts")
@require_POST
def idea_edit(request, workspace_id, idea_id):
    """Edit an existing idea via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    idea = get_object_or_404(Idea, id=idea_id, workspace=workspace)
    previous_group_id = str(idea.group_id) if idea.group_id else ""

    idea.title = request.POST.get("title", idea.title).strip()
    idea.description = request.POST.get("description", idea.description).strip()
    idea.tags = parse_and_truncate_tag_string(request.POST.get("tags", ""))

    group_id = request.POST.get("group", "").strip()
    if group_id:
        group = IdeaGroup.objects.filter(id=group_id, workspace=workspace).first()
        if group:
            idea.group = group

    # Handle media attachments:
    # - preferred: ordered media_asset_ids list
    # - fallback: legacy single media_asset_id + remove_media
    has_multi_media_payload = "media_asset_ids" in request.POST
    media_asset_ids = _normalize_media_asset_ids(request.POST.get("media_asset_ids", ""))
    uploaded_file = request.FILES.get("media") or request.FILES.get("file")
    uploaded_asset = None
    if uploaded_file:
        uploaded_asset = _create_idea_media_asset(workspace, request.user, uploaded_file)
        media_asset_ids.append(str(uploaded_asset.id))
    media_asset_ids = _normalize_media_asset_ids(media_asset_ids)

    with transaction.atomic():
        idea.save(update_fields=["title", "description", "tags", "group", "updated_at"])

        if has_multi_media_payload:
            _sync_idea_media_attachments(idea, workspace, media_asset_ids)
        else:
            media_asset_id = request.POST.get("media_asset_id", "").strip()
            remove_media = request.POST.get("remove_media") == "true"

            if uploaded_asset:
                _sync_idea_media_attachments(idea, workspace, [str(uploaded_asset.id)])
            elif media_asset_id:
                from apps.media_library.models import MediaAsset

                asset = MediaAsset.objects.filter(id=media_asset_id, workspace=workspace).first()
                if asset:
                    _sync_idea_media_attachments(idea, workspace, [str(asset.id)])
            elif remove_media:
                _sync_idea_media_attachments(idea, workspace, [])

    # Sync any new tags to the Tag model
    editor.sync_tags_to_model(workspace, idea.tags)

    if _wants_json_response(request):
        idea = (
            Idea.objects.for_workspace(workspace.id)
            .select_related("media_asset")
            .prefetch_related("media_attachments__media_asset")
            .get(id=idea.id)
        )
        return JsonResponse(
            {
                "ok": True,
                "idea_id": str(idea.id),
                "previous_group_id": previous_group_id,
                "group_id": str(idea.group_id) if idea.group_id else "",
                "tags": idea.tags or [],
                "card_html": _render_idea_card_fragment(request, idea),
            }
        )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "ideaChanged"},
    )


@login_required
@require_permission("create_posts")
@require_POST
def idea_delete(request, workspace_id, idea_id):
    """Delete an idea via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    idea = get_object_or_404(Idea, id=idea_id, workspace=workspace)
    group_id = str(idea.group_id) if idea.group_id else ""
    idea.delete()

    if _wants_json_response(request):
        return JsonResponse(
            {
                "ok": True,
                "idea_id": str(idea_id),
                "group_id": group_id,
            }
        )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "ideaChanged"},
    )


@login_required
@require_permission("create_posts")
@require_POST
def idea_move(request, workspace_id, idea_id):
    """Move an idea to a new column/position via HTMX (drag-and-drop)."""
    workspace = _get_workspace(request, workspace_id)
    idea = get_object_or_404(Idea, id=idea_id, workspace=workspace)
    new_group_id = request.POST.get("group")
    new_position = request.POST.get("position")

    # Support both group-based and legacy status-based moves
    if new_group_id:
        group = IdeaGroup.objects.filter(id=new_group_id, workspace=workspace).first()
        if group:
            idea.group = group
    else:
        new_status = request.POST.get("status")
        if new_status and new_status in dict(Idea.Status.choices):
            idea.status = new_status
    if new_position is not None:
        with contextlib.suppress(ValueError, TypeError):
            idea.position = int(new_position)
    idea.save()

    # No HX-Trigger here - the frontend handles the move optimistically
    return HttpResponse(status=204)


@login_required
@require_permission("create_posts")
@require_GET
def idea_board(request, workspace_id):
    """Return the Kanban board partial for HTMX refresh."""
    workspace = _get_workspace(request, workspace_id)
    tag = request.GET.get("tag")
    columns, all_tags = _idea_columns(workspace, tag)

    return render(
        request,
        "composer/partials/kanban_board.html",
        {
            "workspace": workspace,
            "columns": columns,
            "all_tags": all_tags,
            "active_tag": tag,
        },
    )


# ---------------------------------------------------------------------------
# Idea Group CRUD (Kanban columns)
# ---------------------------------------------------------------------------


@login_required
@require_permission("create_posts")
@require_POST
def idea_group_create(request, workspace_id):
    """Create a new Kanban column via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    name = request.POST.get("name", "").strip()
    if not name:
        if _wants_json_response(request):
            return JsonResponse({"error": "Name is required."}, status=400)
        return HttpResponse("Name is required.", status=400)

    max_pos = IdeaGroup.objects.for_workspace(workspace.id).aggregate(models.Max("position"))["position__max"] or 0
    group = IdeaGroup.objects.create(workspace=workspace, name=name, position=max_pos + 1)

    if _wants_json_response(request):
        return JsonResponse(
            {
                "ok": True,
                "group_id": str(group.id),
                "group_name": group.name,
                "column_html": _render_kanban_column_fragment(request, group),
            }
        )

    return HttpResponse(status=204, headers={"HX-Trigger": "ideaChanged"})


@login_required
@require_permission("create_posts")
@require_POST
def idea_group_delete(request, workspace_id, group_id):
    """Delete an empty Kanban column via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    group = get_object_or_404(IdeaGroup, id=group_id, workspace=workspace)

    if group.ideas.exists():
        if _wants_json_response(request):
            return JsonResponse({"error": "Column must be empty before deleting."}, status=400)
        return HttpResponse("Column must be empty before deleting.", status=400)

    deleted_group_id = str(group.id)
    group.delete()
    if _wants_json_response(request):
        return JsonResponse({"ok": True, "group_id": deleted_group_id})
    return HttpResponse(status=204, headers={"HX-Trigger": "ideaChanged"})


@login_required
@require_permission("create_posts")
@require_POST
def idea_group_reorder(request, workspace_id):
    """Reorder Kanban columns. Expects JSON body: {"order": ["uuid1", "uuid2", ...]}."""
    workspace = _get_workspace(request, workspace_id)
    try:
        data = json.loads(request.body)
        order = data.get("order", [])
    except (json.JSONDecodeError, AttributeError):
        return HttpResponse("Invalid JSON.", status=400)

    if not order:
        return HttpResponse(status=204)

    groups = {str(g.id): g for g in IdeaGroup.objects.for_workspace(workspace.id)}
    for position, group_id in enumerate(order):
        group = groups.get(group_id)
        if group and group.position != position:
            group.position = position
            group.save(update_fields=["position"])

    return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Content Categories CRUD
# ---------------------------------------------------------------------------


@login_required
def category_list(request, workspace_id):
    """Settings page for managing content categories."""
    workspace = _get_workspace(request, workspace_id)
    categories = ContentCategory.objects.for_workspace(workspace.id)
    form = ContentCategoryForm()

    return render(
        request,
        "composer/categories.html",
        {
            "workspace": workspace,
            "categories": categories,
            "form": form,
        },
    )


@login_required
@require_POST
def category_create(request, workspace_id):
    """Create a new content category via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    form = ContentCategoryForm(request.POST)

    if not form.is_valid():
        return HttpResponse("Invalid data.", status=400)

    category = form.save(commit=False)
    category.workspace = workspace
    max_pos = ContentCategory.objects.for_workspace(workspace.id).aggregate(models.Max("position"))["position__max"]
    category.position = (max_pos or 0) + 1
    category.save()

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "categoryChanged"},
    )


@login_required
@require_POST
def category_edit(request, workspace_id, category_id):
    """Edit a content category via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    category = get_object_or_404(ContentCategory, id=category_id, workspace=workspace)
    form = ContentCategoryForm(request.POST, instance=category)

    if not form.is_valid():
        return HttpResponse("Invalid data.", status=400)

    form.save()
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "categoryChanged"},
    )


@login_required
@require_POST
def category_delete(request, workspace_id, category_id):
    """Delete a content category via HTMX."""
    workspace = _get_workspace(request, workspace_id)
    category = get_object_or_404(ContentCategory, id=category_id, workspace=workspace)
    category.delete()

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "categoryChanged"},
    )


# ---------------------------------------------------------------------------
# Post Templates
# ---------------------------------------------------------------------------


@login_required
def template_list(request, workspace_id):
    """Settings page for managing post templates."""
    workspace = _get_workspace(request, workspace_id)
    templates = PostTemplate.objects.for_workspace(workspace.id).select_related("created_by")

    return render(
        request,
        "composer/templates_list.html",
        {
            "workspace": workspace,
            "templates": templates,
        },
    )


@login_required
@require_POST
def save_as_template(request, workspace_id, post_id):
    """Save the current post as a reusable template."""
    workspace = _get_workspace(request, workspace_id)
    post = get_object_or_404(Post, id=post_id, workspace=workspace)

    name = request.POST.get("template_name", "").strip()
    if not name:
        name = f"Template from {post.caption_snippet or 'post'}"

    description = request.POST.get("template_description", "").strip()

    template_data = {
        "caption": post.caption,
        "first_comment": post.first_comment,
        "category_id": str(post.category_id) if post.category_id else None,
        "tags": post.tags,
        "platform_account_ids": [str(pp.social_account_id) for pp in post.platform_posts.all()],
        "media_asset_ids": [str(pm.media_asset_id) for pm in post.media_attachments.all()],
    }

    PostTemplate.objects.create(
        workspace=workspace,
        name=name,
        description=description,
        template_data=template_data,
        created_by=request.user,
    )

    if request.htmx:
        return HttpResponse(
            status=204,
            headers={"HX-Trigger": "templateSaved"},
        )
    return redirect("composer:compose_edit", workspace_id=workspace.id, post_id=post.id)


@login_required
@require_POST
def template_delete(request, workspace_id, template_id):
    """Delete a post template."""
    workspace = _get_workspace(request, workspace_id)
    tpl = get_object_or_404(PostTemplate, id=template_id, workspace=workspace)
    tpl.delete()

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "templateChanged"},
    )


@login_required
@require_GET
def template_picker(request, workspace_id):
    """HTMX partial returning list of templates for the picker modal."""
    workspace = _get_workspace(request, workspace_id)
    templates = PostTemplate.objects.for_workspace(workspace.id).select_related("created_by")

    return render(
        request,
        "composer/partials/template_picker.html",
        {
            "workspace": workspace,
            "templates": templates,
        },
    )


@login_required
@require_GET
def use_template(request, workspace_id, template_id):
    """Redirect to composer with template data pre-filled."""
    workspace = _get_workspace(request, workspace_id)
    get_object_or_404(PostTemplate, id=template_id, workspace=workspace)

    from django.urls import reverse

    compose_url = reverse("composer:compose", kwargs={"workspace_id": workspace.id})
    return redirect(f"{compose_url}?template={template_id}")


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tag CRUD (JSON API endpoints)
# ---------------------------------------------------------------------------


@login_required
@require_GET
def tag_list(request, workspace_id):
    """Return workspace tags as JSON, optionally filtered by search query."""
    workspace = _get_workspace(request, workspace_id)
    q = request.GET.get("q", "").strip().lower()
    tags = Tag.objects.for_workspace(workspace.id)
    if q:
        tags = tags.filter(name__icontains=q)
    tag_data = [{"id": str(t.id), "name": t.name} for t in tags[:50]]
    return JsonResponse(tag_data, safe=False)


@login_required
@require_POST
def tag_create(request, workspace_id):
    """Create a new tag and return it as JSON."""
    workspace = _get_workspace(request, workspace_id)
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Tag name is required."}, status=400)
    tag, created = Tag.objects.get_or_create(workspace=workspace, name=name)
    return JsonResponse({"id": str(tag.id), "name": tag.name, "created": created})


# ── Feeds ──────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Ideas, feeds, Unsplash, platform lookups and CSV import delegate to the
# composer service modules shared with the web API.
# ---------------------------------------------------------------------------

MAX_CSV_UPLOAD_BYTES = csv_import.MAX_UPLOAD_BYTES
_validate_rss_url = feeds.validate_rss_url


def _prepare_idea_for_kanban(idea):
    """Attach computed media/tag fields used by Kanban templates."""
    media_payload = ideas.idea_media(idea)
    idea.media_payload_json = json.dumps(media_payload)
    idea.tags_payload_json = json.dumps(idea.tags or [])
    idea.media_count = len(media_payload)
    attachments = [att for att in idea.media_attachments.all() if att.media_asset_id and att.media_asset]
    idea.cover_media = attachments[0].media_asset if attachments else idea.media_asset
    return idea


def _idea_columns(workspace, tag=None):
    columns, all_tags = ideas.columns(workspace, tag)
    for col in columns:
        for idea in col["ideas"]:
            _prepare_idea_for_kanban(idea)
    return columns, all_tags


_normalize_media_asset_ids = ideas.normalize_media_ids
_sync_idea_media_attachments = ideas.sync_media
_create_idea_media_asset = ideas.create_media_asset


@login_required
@require_permission("create_posts")
@require_POST
def idea_upload_media(request, workspace_id):
    """Upload media for Idea modals and return an asset id for reliable save binding."""
    workspace = _get_workspace(request, workspace_id)
    uploaded_file = request.FILES.get("file") or request.FILES.get("media")
    if not uploaded_file:
        return JsonResponse({"error": "No file provided"}, status=400)
    asset = ideas.create_media_asset(workspace, request.user, uploaded_file)
    return JsonResponse(
        {
            "asset_id": str(asset.id),
            "filename": asset.filename,
            "url": asset.file.url if asset.file else "",
            "size": asset.file_size,
            "media_type": asset.media_type,
        }
    )


@login_required
@require_permission("create_posts")
@require_POST
def idea_create_post(request, workspace_id, idea_id):
    """Create a new draft post from an idea and return composer redirect metadata."""
    from django.urls import reverse

    workspace = _get_workspace(request, workspace_id)
    idea = get_object_or_404(
        Idea.objects.for_workspace(workspace.id)
        .select_related("media_asset")
        .prefetch_related("media_attachments__media_asset"),
        id=idea_id,
    )
    post = ideas.create_post_from_idea(idea, workspace, request.user)
    compose_url = reverse("composer:compose_edit", kwargs={"workspace_id": workspace.id, "post_id": post.id})
    return JsonResponse({"ok": True, "post_id": str(post.id), "compose_url": compose_url})


@login_required
@require_GET
def unsplash_search(request, workspace_id):
    """Proxy an Unsplash photo search so the API key stays server-side."""
    _get_workspace(request, workspace_id)
    try:
        return JsonResponse(unsplash.search(request.GET.get("q", "")))
    except unsplash.UnsplashError as exc:
        return JsonResponse({"error": exc.message}, status=exc.status)


@login_required
@require_POST
def unsplash_import(request, workspace_id, post_id=None):
    """Download selected Unsplash photos server-side and attach them as media."""
    workspace = _get_workspace(request, workspace_id)
    if not unsplash.enabled():
        return JsonResponse({"error": unsplash.NOT_CONFIGURED}, status=503)
    try:
        photos = json.loads(request.body)["photos"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"error": "Invalid request body"}, status=400)
    post = get_object_or_404(Post, id=post_id, workspace=workspace) if post_id else None
    try:
        new_assets, failed = unsplash.import_photos(workspace, request.user, photos)
    except unsplash.UnsplashError as exc:
        return JsonResponse({"error": exc.message}, status=exc.status)
    attachments = [
        a for a in (_attach_asset_for_composer(request, workspace, asset, post) for asset in new_assets) if a
    ]
    if post is not None:
        html = render_to_string(
            "composer/partials/media_list.html",
            {"media_attachments": attachments, "post": post, "workspace": workspace},
            request=request,
        )
    else:
        html = render_to_string(
            "composer/partials/media_list_pending.html",
            {"pending_assets": new_assets, "workspace": workspace},
            request=request,
        )
    return JsonResponse(
        {"html": html, "assets": [{"id": str(a.id), "url": a.file.url} for a in new_assets], "failed": failed}
    )


@login_required
@require_GET
def pinterest_boards(request, workspace_id, account_id):
    """Fetch Pinterest boards for board selection in the composer."""
    workspace = _get_workspace(request, workspace_id)
    account = get_object_or_404(SocialAccount, id=account_id, workspace=workspace, platform="pinterest")
    try:
        return JsonResponse({"boards": platform_info.pinterest_boards(workspace, account)})
    except RuntimeError as exc:
        return JsonResponse({"error": str(exc)}, status=502)


@login_required
@require_GET
def tiktok_creator_info(request, workspace_id, account_id):
    """Fetch TikTok creator info for the composer's TikTok settings panel."""
    workspace = _get_workspace(request, workspace_id)
    account = get_object_or_404(SocialAccount, id=account_id, workspace=workspace, platform="tiktok")
    return JsonResponse(platform_info.tiktok_creator_info(workspace, account))


@login_required
@require_permission("create_posts")
def csv_upload(request, workspace_id):
    """Render CSV upload page or handle file upload and show column mapping."""
    workspace = _get_workspace(request, workspace_id)
    if request.method == "POST" and request.FILES.get("csv_file"):
        csv_file = request.FILES["csv_file"]
        try:
            headers, rows = csv_import.parse_upload(csv_file)
        except ValueError as exc:
            return render(request, "composer/csv_import.html", {"workspace": workspace, "error": str(exc)})
        request.session[f"csv_import_{workspace.id}"] = {"headers": headers, "rows": rows, "filename": csv_file.name}
        return render(
            request,
            "composer/partials/csv_mapping.html",
            {
                "workspace": workspace,
                "headers": headers,
                "preview_rows": rows[:5],
                "auto_mapping": csv_import.auto_mapping(headers),
                "field_choices": csv_import.FIELDS,
            },
        )
    return render(request, "composer/csv_import.html", {"workspace": workspace})


@login_required
@require_permission("create_posts")
@require_POST
def csv_preview(request, workspace_id):
    """Validate CSV rows with the selected column mapping and show preview."""
    workspace = _get_workspace(request, workspace_id)
    csv_data = request.session.get(f"csv_import_{workspace.id}")
    if not csv_data:
        return HttpResponse("No CSV data found. Please upload again.", status=400)
    mapping = csv_import.clean_mapping({f: request.POST.get(f"map_{f}", "") for f in csv_import.FIELDS})
    request.session[f"csv_mapping_{workspace.id}"] = mapping
    context = csv_import.validate_rows(workspace, csv_data["rows"], mapping)
    return render(request, "composer/partials/csv_validation.html", {"workspace": workspace, **context})


@login_required
@require_permission("create_posts")
@require_POST
def csv_confirm_import(request, workspace_id):
    """Kick off the CSV import."""
    workspace = _get_workspace(request, workspace_id)
    csv_data = request.session.get(f"csv_import_{workspace.id}")
    mapping = request.session.get(f"csv_mapping_{workspace.id}")
    if not csv_data or not mapping:
        return HttpResponse("No CSV data found. Please upload again.", status=400)
    result = csv_import.import_rows(workspace, request.user, csv_data["rows"], mapping)
    request.session.pop(f"csv_import_{workspace.id}", None)
    request.session.pop(f"csv_mapping_{workspace.id}", None)
    return render(request, "composer/partials/csv_progress.html", {"workspace": workspace, **result})


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


def _render_feeds_tab(
    request, workspace, *, show_add_modal=False, add_rss_url="", add_error="", selected_feed_id="all"
):
    context = feeds.events_context(workspace, selected_feed_id=selected_feed_id, offset=0)
    context.update(
        {"workspace": workspace, "show_add_modal": show_add_modal, "add_rss_url": add_rss_url, "add_error": add_error}
    )
    return render(request, "composer/partials/feeds_tab.html", context)


def _render_explore(request, workspace, category):
    return render(
        request, "composer/partials/feeds_explore.html", {"workspace": workspace, **feeds.explore(workspace, category)}
    )


@login_required
@require_permission("create_posts")
@require_GET
def feed_list(request, workspace_id):
    """Return the feeds tab partial (empty state or feed list)."""
    workspace = _get_workspace(request, workspace_id)
    selected_feed_id = request.GET.get("feed_id", "all")
    if request.GET.get("append") == "1":
        offset = feeds.coerce_positive_int(request.GET.get("offset"), default=0)
        context = feeds.events_context(workspace, selected_feed_id=selected_feed_id, offset=offset)
        context.update({"workspace": workspace, "show_empty": False})
        return render(request, "composer/partials/feed_events_batch.html", context)
    return _render_feeds_tab(request, workspace, selected_feed_id=selected_feed_id)


@login_required
@require_permission("create_posts")
@require_POST
def feed_add(request, workspace_id):
    """Add a feed subscription to the workspace."""
    workspace = _get_workspace(request, workspace_id)
    rss_url = request.POST.get("rss_url", "").strip()
    source = request.POST.get("source", "")
    category = request.POST.get("category", "osir-favorites")
    selected_feed_id = request.POST.get("feed_id", "all")
    try:
        feeds.add_feed(
            workspace,
            request.user,
            rss_url,
            name=request.POST.get("name", "").strip(),
            website_url=request.POST.get("website_url", "").strip(),
            validate=source != "explore",
        )
    except ValueError as exc:
        if source == "explore":
            if str(exc) == "Already subscribed to this feed.":
                return _render_explore(request, workspace, category)
            return HttpResponse(str(exc), status=400)
        return _render_feeds_tab(
            request,
            workspace,
            show_add_modal=True,
            add_rss_url=rss_url,
            add_error=str(exc),
            selected_feed_id=selected_feed_id,
        )
    if source == "explore":
        response = _render_explore(request, workspace, category)
        response["HX-Trigger"] = "feedsUpdated"
        return response
    return _render_feeds_tab(request, workspace, selected_feed_id=selected_feed_id)


@login_required
@require_permission("create_posts")
@require_POST
def feed_delete(request, workspace_id, feed_id):
    """Remove a feed subscription."""
    workspace = _get_workspace(request, workspace_id)
    selected_feed_id = request.POST.get("feed_id", "all")
    feeds.remove_feed(get_object_or_404(Feed, id=feed_id, workspace=workspace))
    return _render_feeds_tab(request, workspace, selected_feed_id=selected_feed_id)


@login_required
@require_permission("create_posts")
@require_GET
def feed_explore(request, workspace_id):
    """Return the explore feeds modal content for a given category."""
    workspace = _get_workspace(request, workspace_id)
    return _render_explore(request, workspace, request.GET.get("category", "osir-favorites"))
