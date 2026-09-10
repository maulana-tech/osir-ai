"""Helpers shared by the web API routers."""

from __future__ import annotations

import uuid

from django.http import HttpRequest
from ninja.errors import HttpError

from apps.members.models import WorkspaceMembership


def scoped(request: HttpRequest, workspace_id: uuid.UUID) -> WorkspaceMembership:
    """Resolve the caller's membership in ``workspace_id`` or 404.

    Workspace-scoped web routes carry the workspace in the URL, so the URL wins
    over the ``X-Workspace-Id`` header the session auth used. Sets
    ``request.workspace`` / ``request.workspace_membership`` to match so the
    shared permission helpers see the right scope.
    """
    membership = (
        WorkspaceMembership.objects.select_related("workspace", "workspace__organization", "custom_role")
        .filter(user=request.user, workspace_id=workspace_id, workspace__is_archived=False)  # type: ignore[misc]
        .first()
    )
    if membership is None:
        raise HttpError(404, "Workspace not found")
    request.workspace = membership.workspace  # type: ignore[attr-defined]
    request.workspace_membership = membership  # type: ignore[attr-defined]
    return membership


def require_perm(membership: WorkspaceMembership, key: str) -> None:
    if not membership.effective_permissions.get(key, False):
        raise HttpError(403, f"Permission denied: {key}")
