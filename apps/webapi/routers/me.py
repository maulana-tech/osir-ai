"""Who am I, where can I go: the data the app shell needs on every page."""

from __future__ import annotations

import uuid

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.members.models import OrgMembership, WorkspaceMembership

router = Router(tags=["me"])


def _workspace_entry(m: WorkspaceMembership) -> dict:
    ws = m.workspace
    return {
        "id": str(ws.id),
        "name": ws.name,
        "role": m.custom_role.name if m.custom_role_id else m.workspace_role,
        "timezone": ws.timezone or "UTC",
        "agent_autonomy": ws.agent_autonomy,
        "approval_workflow_mode": ws.approval_workflow_mode,
        "permissions": sorted(k for k, v in m.effective_permissions.items() if v),
    }


@router.get("/", summary="Current user, organization, and workspaces")
def me(request):
    user = request.user
    org_membership = OrgMembership.objects.select_related("organization").filter(user=user).first()
    memberships = (
        WorkspaceMembership.objects.filter(user=user, workspace__is_archived=False)
        .select_related("workspace", "custom_role")
        .order_by("workspace__name")
    )
    current = request.workspace  # chosen by WebSessionAuth (header or last-used)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "avatar_url": user.avatar.url if user.avatar else "",
            "tos_accepted": user.tos_accepted_at is not None,
            "totp_enabled": user.totp_enabled,
        },
        "organization": (
            {
                "id": str(org_membership.organization_id),
                "name": org_membership.organization.name,
                "role": org_membership.org_role,
                "can_create_workspace": org_membership.org_role in ("owner", "admin"),
            }
            if org_membership
            else None
        ),
        "current_workspace_id": str(current.id) if current else None,
        "workspaces": [_workspace_entry(m) for m in memberships],
    }


class SelectWorkspace(Schema):
    workspace_id: uuid.UUID


@router.post("/workspace", summary="Remember the workspace the user is working in")
def select_workspace(request, payload: SelectWorkspace):
    if not WorkspaceMembership.objects.filter(
        user=request.user, workspace_id=payload.workspace_id, workspace__is_archived=False
    ).exists():
        raise HttpError(404, "Workspace not found")
    request.user.last_workspace_id = payload.workspace_id
    request.user.save(update_fields=["last_workspace_id"])
    return {"current_workspace_id": str(payload.workspace_id)}
