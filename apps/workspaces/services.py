"""Workspace lifecycle shared by the HTMX views and the web API."""

from __future__ import annotations

from django.db import transaction

from apps.members.models import WorkspaceMembership

from .models import Workspace

ICON_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
ICON_MAX_BYTES = 2 * 1024 * 1024


def create_workspace(organization, user, name: str) -> Workspace:
    name = name.strip()
    if not name:
        raise ValueError("Workspace name is required.")
    workspace = Workspace.objects.create(organization=organization, name=name)
    WorkspaceMembership.objects.create(
        user=user, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    user.last_workspace_id = workspace.id
    user.save(update_fields=["last_workspace_id"])
    return workspace


def _active_count_locked(workspace) -> int:
    return Workspace.objects.select_for_update().filter(organization=workspace.organization, is_archived=False).count()


def archive_workspace(workspace) -> None:
    with transaction.atomic():
        if _active_count_locked(workspace) <= 1:
            raise ValueError("Cannot archive the last workspace in the organization.")
        workspace.is_archived = True
        workspace.save(update_fields=["is_archived"])


def unarchive_workspace(workspace) -> None:
    workspace.is_archived = False
    workspace.save(update_fields=["is_archived"])


def delete_workspace(workspace) -> str:
    with transaction.atomic():
        if _active_count_locked(workspace) <= 1 and not workspace.is_archived:
            raise ValueError("Cannot delete the last workspace in the organization.")
        name = workspace.name
        workspace.delete()
    return name


def validate_icon(upload) -> None:
    if upload.content_type not in ICON_TYPES:
        raise ValueError("Logo must be a JPEG, PNG, WebP, or GIF image.")
    if upload.size > ICON_MAX_BYTES:
        raise ValueError("Logo must be under 2 MB.")
