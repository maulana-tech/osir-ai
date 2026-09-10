"""The Ideas kanban: columns, idea media, and turning an idea into a draft post."""

from __future__ import annotations

import uuid

from django.db import models, transaction
from django.utils import timezone

from apps.social_accounts.models import SocialAccount

from .models import Idea, IdeaGroup, IdeaMedia, PlatformPost, Post, PostMedia, Tag

DEFAULT_GROUPS = [("Unassigned", 0), ("To Do", 1), ("In Progress", 2), ("Done", 3)]


def ensure_default_groups(workspace):
    groups = IdeaGroup.objects.for_workspace(workspace.id).order_by("position", "created_at")
    if groups.exists():
        return groups
    created = {
        name: IdeaGroup.objects.create(workspace=workspace, name=name, position=pos) for name, pos in DEFAULT_GROUPS
    }
    Idea.objects.create(
        workspace=workspace,
        group=created["Unassigned"],
        title="This is a place to plan ✍️ your content",
        description=(
            "Save your Ideas before converting them into posts. Brainstorm, plan ahead, "
            "and keep everything organized in one place."
        ),
        status=Idea.Status.UNASSIGNED,
        position=0,
    )
    return IdeaGroup.objects.for_workspace(workspace.id).order_by("position", "created_at")


def idea_media(idea) -> list[dict]:
    """Ordered media payload for an idea (legacy single pointer as fallback)."""
    out = []
    for att in idea.media_attachments.all():
        a = att.media_asset
        if a is None:
            continue
        out.append(
            {
                "asset_id": str(a.id),
                "url": a.file.url if a.file else "",
                "thumbnail_url": a.thumbnail.url if a.thumbnail else None,
                "filename": a.filename,
                "media_type": a.media_type,
                "position": att.position,
            }
        )
    if not out and idea.media_asset_id and idea.media_asset:
        a = idea.media_asset
        out.append(
            {
                "asset_id": str(a.id),
                "url": a.file.url if a.file else "",
                "thumbnail_url": a.thumbnail.url if a.thumbnail else None,
                "filename": a.filename,
                "media_type": a.media_type,
                "position": 0,
            }
        )
    return out


def ideas_queryset(workspace, tag=None):
    qs = (
        Idea.objects.for_workspace(workspace.id)
        .select_related("author", "media_asset")
        .prefetch_related("media_attachments__media_asset")
        .order_by("position", "-created_at")
    )
    return qs.filter(tags__contains=[tag]) if tag else qs


def columns(workspace, tag=None) -> tuple[list[dict], list[str]]:
    """``([{id, label, ideas: [Idea]}], all_tag_names)``; seeds the default columns on first use."""
    groups = list(ensure_default_groups(workspace))
    grouped: dict[str, list] = {str(g.id): [] for g in groups}
    for idea in ideas_queryset(workspace, tag):
        key = str(idea.group_id) if idea.group_id else ""
        if key in grouped:
            grouped[key].append(idea)
    cols = [{"id": str(g.id), "key": str(g.id), "label": g.name, "ideas": grouped[str(g.id)]} for g in groups]
    return cols, list(Tag.objects.for_workspace(workspace.id).values_list("name", flat=True))


def normalize_media_ids(raw="", extra=None) -> list[str]:
    """Ordered, de-duplicated UUID strings from a CSV string and/or iterables."""
    chunks: list[str] = []
    if isinstance(raw, str):
        chunks.append(raw)
    elif raw:
        chunks.extend(str(x) for x in raw)
    if extra:
        chunks.extend(str(x) for x in extra)
    out: list[str] = []
    seen: set[str] = set()
    for token in ",".join(chunks).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            norm = str(uuid.UUID(token))
        except (ValueError, TypeError, AttributeError):
            continue
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def sync_media(idea, workspace, ordered_ids) -> None:
    """Make IdeaMedia rows match ``ordered_ids`` and keep the cover pointer aligned."""
    from apps.media_library.models import MediaAsset

    ids = normalize_media_ids(ordered_ids)
    if ids:
        valid = {
            str(a) for a in MediaAsset.objects.filter(workspace=workspace, id__in=ids).values_list("id", flat=True)
        }
        ids = [i for i in ids if i in valid]
    existing = {str(att.media_asset_id): att for att in idea.media_attachments.all()}
    IdeaMedia.objects.filter(id__in=[att.id for k, att in existing.items() if k not in set(ids)]).delete()
    now = timezone.now()
    to_create, to_update = [], []
    for position, asset_id in enumerate(ids):
        att = existing.get(asset_id)
        if att is None:
            to_create.append(IdeaMedia(idea=idea, media_asset_id=asset_id, position=position))
        elif att.position != position:
            att.position = position
            att.updated_at = now
            to_update.append(att)
    if to_create:
        IdeaMedia.objects.bulk_create(to_create)
    if to_update:
        IdeaMedia.objects.bulk_update(to_update, ["position", "updated_at"])
    cover = ids[0] if ids else None
    if (str(idea.media_asset_id) if idea.media_asset_id else None) != cover:
        idea.media_asset_id = cover
        idea.save(update_fields=["media_asset", "updated_at"])


def create_media_asset(workspace, user, uploaded_file):
    from apps.media_library.models import MediaAsset

    content_type = uploaded_file.content_type or ""
    if content_type == "image/gif":
        media_type = MediaAsset.MediaType.GIF
    elif content_type.startswith("image/"):
        media_type = MediaAsset.MediaType.IMAGE
    elif content_type.startswith("video/"):
        media_type = MediaAsset.MediaType.VIDEO
    else:
        media_type = MediaAsset.MediaType.DOCUMENT
    return MediaAsset.objects.create(
        organization=workspace.organization,
        workspace=workspace,
        uploaded_by=user,
        file=uploaded_file,
        filename=uploaded_file.name,
        media_type=media_type,
        mime_type=content_type,
        file_size=uploaded_file.size,
        source="upload",
    )


def create_post_from_idea(idea, workspace, user) -> Post:
    """A draft post carrying the idea's title, description, tags and media, targeting every connected account."""
    tags = [t.strip() for t in (idea.tags or []) if isinstance(t, str) and t.strip()]
    media_ids = []
    seen: set[str] = set()
    for att in idea.media_attachments.all():
        if att.media_asset_id and str(att.media_asset_id) not in seen:
            seen.add(str(att.media_asset_id))
            media_ids.append(str(att.media_asset_id))
    if not media_ids and idea.media_asset_id:
        media_ids.append(str(idea.media_asset_id))
    accounts = list(
        SocialAccount.objects.for_workspace(workspace.id)
        .filter(connection_status=SocialAccount.ConnectionStatus.CONNECTED)
        .order_by("platform", "account_name", "id")
    )
    with transaction.atomic():
        post = Post.objects.create(
            workspace=workspace, author=user, title=idea.title or "", caption=idea.description or "", tags=tags
        )
        if media_ids:
            PostMedia.objects.bulk_create(
                [PostMedia(post=post, media_asset_id=a, position=i) for i, a in enumerate(media_ids)]
            )
        if accounts:
            PlatformPost.objects.bulk_create([PlatformPost(post=post, social_account=a) for a in accounts])
        idea.post = post
        idea.save(update_fields=["post", "updated_at"])
    return post


def next_group_position(workspace) -> int:
    return (IdeaGroup.objects.for_workspace(workspace.id).aggregate(models.Max("position"))["position__max"] or 0) + 1
