"""Approval actions beyond approve/reject: request changes, resume, bulk, comments, versions."""

from __future__ import annotations

import uuid

from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.approvals import comments as comment_service
from apps.approvals import services
from apps.approvals.models import PostComment
from apps.composer.models import Post, PostVersion
from apps.webapi.common import require_perm, scoped

router = Router(tags=["approvals"])


def _post(workspace_id, post_id) -> Post:
    try:
        return Post.objects.get(id=post_id, workspace_id=workspace_id)
    except Post.DoesNotExist as exc:
        raise HttpError(404, "Post not found") from exc


class Comment(Schema):
    comment: str = ""


def _act(request, workspace_id, post_id, fn, *args):
    m = scoped(request, workspace_id)
    require_perm(m, "approve_posts")
    post = _post(workspace_id, post_id)
    try:
        moved = fn(post, request.user, m.workspace, *args)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    if not moved:
        raise HttpError(409, "This post was already actioned.")
    post.refresh_from_db()
    return {
        "post_id": str(post.id),
        "status": post.status,
        "platform_statuses": [pp.status for pp in post.platform_posts.all()],
    }


@router.post("/{workspace_id}/approvals/{uuid:post_id}/request-changes", summary="Send back for changes")
def request_changes(request, workspace_id: uuid.UUID, post_id: uuid.UUID, payload: Comment):
    return _act(request, workspace_id, post_id, services.request_changes, payload.comment)


@router.post("/{workspace_id}/approvals/{uuid:post_id}/resume", summary="Lift a client hold")
def resume(request, workspace_id: uuid.UUID, post_id: uuid.UUID):
    return _act(request, workspace_id, post_id, services.resume_hold)


class Bulk(Schema):
    post_ids: list[uuid.UUID]
    action: str
    comment: str = ""


@router.post("/{workspace_id}/approvals/bulk", summary="Bulk approve or reject")
def bulk(request, workspace_id: uuid.UUID, payload: Bulk):
    m = scoped(request, workspace_id)
    require_perm(m, "approve_posts")
    ids = [str(i) for i in payload.post_ids]
    if not ids:
        raise HttpError(400, "No posts selected")
    try:
        if payload.action == "approve":
            results = services.bulk_approve(ids, request.user, m.workspace)
        elif payload.action == "reject":
            results = services.bulk_reject(ids, request.user, m.workspace, payload.comment)
        else:
            raise HttpError(400, "Invalid action")
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {
        "updated": sum(1 for _, ok, _ in results if ok),
        "results": [{"post_id": str(p), "ok": ok, "detail": d} for p, ok, d in results],
    }


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def _comment(c: PostComment) -> dict:
    return {
        "id": str(c.id),
        "author": c.author.display_name if c.author else None,
        "author_id": str(c.author_id) if c.author_id else None,
        "body": c.body,
        "visibility": c.visibility,
        "attachment_url": c.attachment.url if c.attachment else "",
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
        "replies": [_comment(r) for r in c.replies.all() if r.deleted_at is None] if hasattr(c, "replies") else [],
    }


@router.get("/{workspace_id}/posts/{uuid:post_id}/comments", summary="Comment thread on a post")
def comments(request, workspace_id: uuid.UUID, post_id: uuid.UUID):
    scoped(request, workspace_id)
    post = _post(workspace_id, post_id)
    return {"comments": [_comment(c) for c in comment_service.get_comments_for_post(post, request.user)]}


class CommentIn(Schema):
    body: str
    visibility: str = PostComment.Visibility.EXTERNAL
    parent_id: uuid.UUID | None = None


@router.post("/{workspace_id}/posts/{uuid:post_id}/comments", summary="Add a comment")
def comment_add(request, workspace_id: uuid.UUID, post_id: uuid.UUID, payload: CommentIn):
    scoped(request, workspace_id)
    post = _post(workspace_id, post_id)
    body = payload.body.strip()
    if not body:
        raise HttpError(400, "Comment body is required.")
    if payload.visibility not in PostComment.Visibility.values:
        raise HttpError(400, "Invalid visibility")
    c = comment_service.create_comment(post, request.user, body, payload.visibility, parent_id=payload.parent_id)
    return _comment(c)


class CommentEdit(Schema):
    body: str


@router.put("/{workspace_id}/posts/{uuid:post_id}/comments/{uuid:comment_id}", summary="Edit my comment")
def comment_edit(request, workspace_id: uuid.UUID, post_id: uuid.UUID, comment_id: uuid.UUID, payload: CommentEdit):
    m = scoped(request, workspace_id)
    _post(workspace_id, post_id)
    body = payload.body.strip()
    if not body:
        raise HttpError(400, "Comment body is required.")
    try:
        c = comment_service.update_comment(comment_id, request.user, body, workspace=m.workspace)
    except (ValueError, PermissionError) as exc:
        raise HttpError(403, str(exc)) from exc
    return _comment(c)


@router.delete("/{workspace_id}/posts/{uuid:post_id}/comments/{uuid:comment_id}", summary="Delete my comment")
def comment_delete(request, workspace_id: uuid.UUID, post_id: uuid.UUID, comment_id: uuid.UUID):
    m = scoped(request, workspace_id)
    _post(workspace_id, post_id)
    try:
        comment_service.delete_comment(comment_id, request.user, m.workspace)
    except (ValueError, PermissionError) as exc:
        raise HttpError(403, str(exc)) from exc
    return {"deleted": True, "at": timezone.now().isoformat()}


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/posts/{uuid:post_id}/versions", summary="Version history with a diff")
def versions(request, workspace_id: uuid.UUID, post_id: uuid.UUID, v1: int | None = None, v2: int | None = None):
    scoped(request, workspace_id)
    post = _post(workspace_id, post_id)
    all_versions = list(PostVersion.objects.filter(post=post).select_related("created_by").order_by("-version_number"))
    old = new = None
    if v1 and v2:
        old = next((v for v in all_versions if v.version_number == v1), None)
        new = next((v for v in all_versions if v.version_number == v2), None)
    elif len(all_versions) >= 2:
        new, old = all_versions[0], all_versions[1]
    elif all_versions:
        new = all_versions[0]
    return {
        "versions": [
            {
                "number": v.version_number,
                "created_by": v.created_by.display_name if v.created_by else None,
                "created_at": v.created_at.isoformat(),
            }
            for v in all_versions
        ],
        "old": old.version_number if old else None,
        "new": new.version_number if new else None,
        "diff": services.build_diff(old.snapshot if old else {}, new.snapshot if new else {}),
    }
