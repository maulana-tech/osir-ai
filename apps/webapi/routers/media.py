"""Media library: the workspace library and the organization's shared library."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.common.validators import normalize_tags
from apps.media_library import services
from apps.media_library.models import MediaAsset, MediaAssetVersion, MediaFolder
from apps.media_library.quotas import StorageQuotaExceededError
from apps.media_library.tasks import process_media_asset
from apps.media_library.validators import get_accepted_file_types
from apps.members.models import OrgMembership
from apps.webapi.common import require_perm, scoped

router = Router(tags=["media"])
org_router = Router(tags=["media"])

PAGE_SIZE = 48


def _asset(a: MediaAsset) -> dict:
    return {
        "id": str(a.id),
        "filename": a.filename,
        "media_type": a.media_type,
        "mime_type": a.mime_type,
        "file_size": a.file_size,
        "file_size_display": a.file_size_display,
        "width": a.width,
        "height": a.height,
        "duration": a.duration,
        "title": a.title,
        "alt_text": a.alt_text,
        "tags": list(a.tags or []),
        "folder_id": str(a.folder_id) if a.folder_id else None,
        "is_starred": a.is_starred,
        "is_shared": a.is_shared,
        "processing_status": a.processing_status,
        "url": a.file.url if a.file else "",
        "thumbnail_url": a.thumbnail.url if a.thumbnail else None,
        "uploaded_by": a.uploaded_by.display_name if a.uploaded_by else None,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


def _version(v: MediaAssetVersion, asset: MediaAsset) -> dict:
    return {
        "id": str(v.id),
        "number": v.version_number,
        "description": v.change_description,
        "thumbnail_url": v.thumbnail.url if v.thumbnail else None,
        "is_current": asset.current_version_id == v.id,
        "created_by": v.created_by.display_name if v.created_by else None,
        "created_at": v.created_at.isoformat(),
    }


def _folder_tree(workspace) -> list[dict]:
    rows = list(MediaFolder.objects.filter(workspace=workspace).order_by("name"))
    children: dict[Any, list] = {}
    for f in rows:
        children.setdefault(f.parent_folder_id, []).append(f)

    def node(f):
        return {"id": str(f.id), "name": f.name, "children": [node(c) for c in children.get(f.id, [])]}

    return [node(f) for f in children.get(None, [])]


def _page(qs, page: int) -> dict:
    p = Paginator(qs, PAGE_SIZE).get_page(page)
    return {
        "assets": [_asset(a) for a in p.object_list],
        "page": p.number,
        "num_pages": p.paginator.num_pages,
        "total": p.paginator.count,
    }


def _upload(files, *, organization, workspace, user, folder=None) -> list[dict]:
    max_bulk = getattr(settings, "MEDIA_LIBRARY_MAX_BULK_UPLOAD", 50)
    if not files:
        raise HttpError(400, "No files provided")
    if len(files) > max_bulk:
        raise HttpError(400, f"Maximum {max_bulk} files per upload")
    results = []
    for f in files:
        try:
            asset = services.create_asset(
                organization=organization, workspace=workspace, uploaded_file=f, uploaded_by=user, folder=folder
            )
        except ValidationError as exc:
            results.append({"filename": f.name, "ok": False, "error": "; ".join(exc.messages)})
            continue
        except StorageQuotaExceededError as exc:
            results.append({"filename": f.name, "ok": False, "error": str(exc)})
            continue
        process_media_asset(str(asset.id))
        results.append({"filename": f.name, "ok": True, "asset": _asset(asset)})
    return results


def _set_tags(asset: MediaAsset, tags: list[str]) -> dict:
    try:
        asset.tags = normalize_tags(tags)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    asset.save(update_fields=["tags", "updated_at"])
    return {"tags": asset.tags}


def _delete(asset: MediaAsset) -> dict:
    try:
        services.delete_asset(asset)
    except services.ProtectedAssetError as exc:
        raise HttpError(
            409,
            "Referenced by scheduled posts: " + "; ".join((p.caption or "")[:60] for p in exc.referencing_posts[:5]),
        ) from exc
    return {"deleted": True}


def _edit(asset: MediaAsset, payload: dict, user) -> dict:
    try:
        version = services.submit_edit(asset, payload, user)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    if version is None:
        raise HttpError(400, "Nothing to apply")
    return _version(version, asset)


# ---------------------------------------------------------------------------
# Workspace library
# ---------------------------------------------------------------------------


def _visible(m):
    ws = m.workspace
    return MediaAsset.objects.for_workspace_with_shared(
        workspace_id=ws.id, organization_id=ws.organization_id
    ).select_related("uploaded_by", "folder")


def _own(m, asset_id) -> MediaAsset:
    """A workspace-owned asset (shared org assets are read-only here)."""
    return get_object_or_404(MediaAsset.objects.for_workspace(m.workspace.id), pk=asset_id)


def _any(m, asset_id) -> MediaAsset:
    return get_object_or_404(_visible(m), pk=asset_id)


@router.get("/{workspace_id}/media", summary="Library page: assets (filtered, paged) and folders")
def library(
    request,
    workspace_id: uuid.UUID,
    q: str = "",
    type: str = "",  # noqa: A002
    folder: str = "",
    starred: str = "",
    uploader: str = "",
    sort: str = "-date",
    page: int = 1,
):
    m = scoped(request, workspace_id)
    params = {"q": q, "type": type, "folder": folder, "starred": starred, "uploader": uploader, "sort": sort}
    perms = m.effective_permissions
    return {
        **_page(services.filter_assets(_visible(m), params), page),
        "folders": _folder_tree(m.workspace),
        "file_types": [{"value": v, "label": label} for v, label in MediaAsset.MediaType.choices],
        "accepted_file_types": get_accepted_file_types(),
        "max_bulk_upload": getattr(settings, "MEDIA_LIBRARY_MAX_BULK_UPLOAD", 50),
        "can": {k: bool(perms.get(k)) for k in ("upload_media", "edit_media", "delete_media", "manage_media")},
    }


@router.post("/{workspace_id}/media/upload", summary="Upload files (multipart: files[], folder_id)")
def upload(
    request,
    workspace_id: uuid.UUID,
    files: list[UploadedFile] = File(...),  # noqa: B008
    folder_id: uuid.UUID | None = Form(None),  # noqa: B008
):
    m = scoped(request, workspace_id)
    require_perm(m, "upload_media")
    folder = get_object_or_404(MediaFolder, pk=folder_id, workspace=m.workspace) if folder_id else None
    return {
        "results": _upload(
            files, organization=m.workspace.organization, workspace=m.workspace, user=request.user, folder=folder
        )
    }


@router.get("/{workspace_id}/media/tags", summary="Tag suggestions")
def tags(request, workspace_id: uuid.UUID, q: str = ""):
    m = scoped(request, workspace_id)
    return {"tags": services.tag_suggestions(_visible(m), q)}


@router.get("/{workspace_id}/media/{uuid:asset_id}", summary="Asset detail with versions")
def detail(request, workspace_id: uuid.UUID, asset_id: uuid.UUID):
    m = scoped(request, workspace_id)
    asset = _any(m, asset_id)
    return {
        "asset": _asset(asset),
        "versions": [_version(v, asset) for v in asset.versions.all()],
        "download_url": f"/workspace/{workspace_id}/media/{asset.id}/download/",
    }


@router.get("/{workspace_id}/media/{uuid:asset_id}/status", summary="Processing status (poll)")
def status(request, workspace_id: uuid.UUID, asset_id: uuid.UUID):
    m = scoped(request, workspace_id)
    return _asset(_any(m, asset_id))


@router.post("/{workspace_id}/media/{uuid:asset_id}/star", summary="Toggle star")
def star(request, workspace_id: uuid.UUID, asset_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "upload_media")
    asset = _any(m, asset_id)
    asset.is_starred = not asset.is_starred
    asset.save(update_fields=["is_starred"])
    return {"is_starred": asset.is_starred}


class TagsIn(Schema):
    tags: list[str]


@router.put("/{workspace_id}/media/{uuid:asset_id}/tags", summary="Replace tags")
def set_tags(request, workspace_id: uuid.UUID, asset_id: uuid.UUID, payload: TagsIn):
    m = scoped(request, workspace_id)
    require_perm(m, "edit_media")
    return _set_tags(_own(m, asset_id), payload.tags)


class MoveIn(Schema):
    folder_id: uuid.UUID | None = None


@router.post("/{workspace_id}/media/{uuid:asset_id}/move", summary="Move to a folder (null = root)")
def move(request, workspace_id: uuid.UUID, asset_id: uuid.UUID, payload: MoveIn):
    m = scoped(request, workspace_id)
    require_perm(m, "edit_media")
    asset = _own(m, asset_id)
    asset.folder = (
        get_object_or_404(MediaFolder, pk=payload.folder_id, workspace=m.workspace) if payload.folder_id else None
    )
    asset.save(update_fields=["folder", "updated_at"])
    return _asset(asset)


@router.delete("/{workspace_id}/media/{uuid:asset_id}", summary="Delete an asset")
def delete(request, workspace_id: uuid.UUID, asset_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "delete_media")
    return _delete(_own(m, asset_id))


class EditIn(Schema):
    crop_x: int | None = None
    crop_y: int | None = None
    crop_width: int | None = None
    crop_height: int | None = None
    rotate: int | None = None
    flip: str | None = None
    resize_width: int | None = None
    resize_height: int | None = None
    trim_start: float | None = None
    trim_end: float | None = None


@router.post("/{workspace_id}/media/{uuid:asset_id}/edit", summary="Crop / rotate / flip / resize or trim")
def edit(request, workspace_id: uuid.UUID, asset_id: uuid.UUID, payload: EditIn):
    m = scoped(request, workspace_id)
    require_perm(m, "edit_media")
    return _edit(_own(m, asset_id), payload.model_dump(exclude_none=True), request.user)


@router.post("/{workspace_id}/media/{uuid:asset_id}/versions/{uuid:version_id}/restore", summary="Restore")
def restore(request, workspace_id: uuid.UUID, asset_id: uuid.UUID, version_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "edit_media")
    asset = _own(m, asset_id)
    version = get_object_or_404(asset.versions, pk=version_id)
    services.restore_version(asset, version, request.user)
    asset.refresh_from_db()
    return {"asset": _asset(asset), "versions": [_version(v, asset) for v in asset.versions.all()]}


class FolderIn(Schema):
    name: str
    parent_folder_id: uuid.UUID | None = None


@router.post("/{workspace_id}/media/folders", summary="Create a folder")
def folder_create(request, workspace_id: uuid.UUID, payload: FolderIn):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_media")
    name = payload.name.strip()
    if not name:
        raise HttpError(400, "Folder name is required")
    parent = (
        get_object_or_404(MediaFolder, pk=payload.parent_folder_id, workspace=m.workspace)
        if payload.parent_folder_id
        else None
    )
    try:
        folder = services.create_folder(m.workspace.organization, m.workspace, name, parent)
    except ValidationError as exc:
        raise HttpError(400, "; ".join(exc.messages)) from exc
    return {"id": str(folder.id), "name": folder.name, "folders": _folder_tree(m.workspace)}


class FolderRename(Schema):
    name: str


@router.patch("/{workspace_id}/media/folders/{uuid:folder_id}", summary="Rename a folder")
def folder_rename(request, workspace_id: uuid.UUID, folder_id: uuid.UUID, payload: FolderRename):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_media")
    folder = get_object_or_404(MediaFolder, pk=folder_id, workspace=m.workspace)
    try:
        services.rename_folder(folder, payload.name)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"id": str(folder.id), "name": folder.name, "folders": _folder_tree(m.workspace)}


@router.delete("/{workspace_id}/media/folders/{uuid:folder_id}", summary="Delete a folder (contents move up)")
def folder_delete(request, workspace_id: uuid.UUID, folder_id: uuid.UUID):
    m = scoped(request, workspace_id)
    require_perm(m, "manage_media")
    services.delete_folder(get_object_or_404(MediaFolder, pk=folder_id, workspace=m.workspace))
    return {"deleted": True, "folders": _folder_tree(m.workspace)}


# ---------------------------------------------------------------------------
# Shared organization library
# ---------------------------------------------------------------------------


def _org(request, admin: bool = False) -> OrgMembership:
    qs = OrgMembership.objects.select_related("organization").filter(user=request.user)
    m = None
    if request.user.last_workspace_id:
        m = qs.filter(organization__workspaces__id=request.user.last_workspace_id).first()
    m = m or qs.first()
    if m is None:
        raise HttpError(404, "No organization")
    if admin and m.org_role not in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN):
        raise HttpError(403, "Only organization admins manage the shared library.")
    return m


def _shared_qs(m):
    return MediaAsset.objects.shared_only(m.organization_id).select_related("uploaded_by")


@org_router.get("/media", summary="Shared library")
def shared_library(request, q: str = "", type: str = "", sort: str = "-date", page: int = 1):  # noqa: A002
    m = _org(request)
    return {
        **_page(services.filter_assets(_shared_qs(m), {"q": q, "type": type, "sort": sort}), page),
        "file_types": [{"value": v, "label": label} for v, label in MediaAsset.MediaType.choices],
        "accepted_file_types": get_accepted_file_types(),
        "max_bulk_upload": getattr(settings, "MEDIA_LIBRARY_MAX_BULK_UPLOAD", 50),
        "is_admin": m.org_role in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN),
    }


@org_router.post("/media/upload", summary="Upload to the shared library (admin)")
def shared_upload(request, files: list[UploadedFile] = File(...)):  # noqa: B008
    m = _org(request, admin=True)
    return {"results": _upload(files, organization=m.organization, workspace=None, user=request.user)}


@org_router.get("/media/tags", summary="Shared tag suggestions")
def shared_tags(request, q: str = ""):
    return {"tags": services.tag_suggestions(_shared_qs(_org(request)), q)}


@org_router.get("/media/{uuid:asset_id}", summary="Shared asset detail")
def shared_detail(request, asset_id: uuid.UUID):
    asset = get_object_or_404(_shared_qs(_org(request)), pk=asset_id)
    return {
        "asset": _asset(asset),
        "versions": [_version(v, asset) for v in asset.versions.all()],
        "download_url": f"/organizations/media/shared/{asset.id}/download/",
    }


@org_router.get("/media/{uuid:asset_id}/status", summary="Shared processing status")
def shared_status(request, asset_id: uuid.UUID):
    return _asset(get_object_or_404(_shared_qs(_org(request)), pk=asset_id))


@org_router.put("/media/{uuid:asset_id}/tags", summary="Replace tags (admin)")
def shared_set_tags(request, asset_id: uuid.UUID, payload: TagsIn):
    return _set_tags(get_object_or_404(_shared_qs(_org(request, admin=True)), pk=asset_id), payload.tags)


@org_router.delete("/media/{uuid:asset_id}", summary="Delete a shared asset (admin)")
def shared_delete(request, asset_id: uuid.UUID):
    return _delete(get_object_or_404(_shared_qs(_org(request, admin=True)), pk=asset_id))


@org_router.post("/media/{uuid:asset_id}/edit", summary="Edit a shared asset (admin)")
def shared_edit(request, asset_id: uuid.UUID, payload: EditIn):
    asset = get_object_or_404(_shared_qs(_org(request, admin=True)), pk=asset_id)
    return _edit(asset, payload.model_dump(exclude_none=True), request.user)
