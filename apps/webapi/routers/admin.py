"""Workspace settings, organization, workspaces, members, clients, and API keys."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import available_timezones

from django.contrib.auth import logout
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.api_keys import services as key_services
from apps.api_keys.models import ApiKey
from apps.api_keys.views import _grantable_permissions
from apps.client_portal import services as portal_services
from apps.client_portal.models import MagicLinkToken
from apps.members import services as member_services
from apps.members.models import Invitation, OrgMembership, WorkspaceMembership
from apps.members.views import _org_role_choices_for
from apps.onboarding.checklist import get_checklist_items
from apps.onboarding.models import OnboardingChecklist
from apps.organizations import services as org_services
from apps.social_accounts.models import SocialAccount
from apps.webapi.common import scoped
from apps.workspaces import services as ws_services
from apps.workspaces.models import Workspace

router = Router(tags=["admin"])

# ---------------------------------------------------------------------------
# Org context helpers
# ---------------------------------------------------------------------------


def _org_membership(request, min_role: str = "member") -> OrgMembership:
    """The caller's organization: the one owning the workspace they were last in, else their first."""
    qs = OrgMembership.objects.select_related("organization").filter(user=request.user)
    m = None
    if request.user.last_workspace_id:
        m = qs.filter(organization__workspaces__id=request.user.last_workspace_id).first()
    m = m or qs.first()
    if m is None:
        raise HttpError(404, "No organization")
    rank = {"owner": 3, "admin": 2, "member": 1}
    if rank.get(m.org_role, 0) < rank[min_role]:
        raise HttpError(403, "Insufficient organization role.")
    return m


def _is_manager(membership: WorkspaceMembership) -> bool:
    return membership.workspace_role in (
        WorkspaceMembership.WorkspaceRole.OWNER,
        WorkspaceMembership.WorkspaceRole.MANAGER,
    )


# ---------------------------------------------------------------------------
# Workspace settings
# ---------------------------------------------------------------------------


def _workspace_payload(ws: Workspace, membership: WorkspaceMembership) -> dict:
    active = Workspace.objects.filter(organization=ws.organization, is_archived=False).count()
    is_last_active = active <= 1 and not ws.is_archived
    manager = _is_manager(membership)
    return {
        "id": str(ws.id),
        "name": ws.name,
        "description": ws.description,
        "icon_url": ws.icon.url if ws.icon else "",
        "timezone": ws.timezone,
        "effective_timezone": ws.effective_timezone,
        "is_archived": ws.is_archived,
        "approval_workflow_mode": ws.approval_workflow_mode,
        "approval_modes": [{"value": v, "label": label} for v, label in Workspace.ApprovalWorkflowMode.choices],
        "agent_autonomy": ws.agent_autonomy,
        "autonomy_levels": [{"value": v, "label": label} for v, label in Workspace.AgentAutonomy.choices],
        "is_owner_or_manager": manager,
        "can_archive": manager and not ws.is_archived and not is_last_active,
        "can_delete": manager and not is_last_active,
        "timezones": sorted(available_timezones()),
    }


@router.get("/{workspace_id}/settings", summary="Workspace settings")
def workspace_settings(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    return _workspace_payload(m.workspace, m)


class WorkspaceUpdate(Schema):
    name: str | None = None
    description: str | None = None
    timezone: str | None = None
    approval_workflow_mode: str | None = None
    agent_autonomy: str | None = None


@router.patch("/{workspace_id}/settings", summary="Update workspace settings")
def workspace_update(request, workspace_id: uuid.UUID, payload: WorkspaceUpdate):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers can change settings.")
    ws = m.workspace
    fields = []
    if payload.name is not None:
        if not payload.name.strip():
            raise HttpError(400, "Name cannot be empty.")
        ws.name = payload.name.strip()
        fields.append("name")
    if payload.description is not None:
        ws.description = payload.description.strip()[:500]
        fields.append("description")
    if payload.timezone is not None:
        if payload.timezone and payload.timezone not in available_timezones():
            raise HttpError(400, "Invalid timezone.")
        ws.timezone = payload.timezone
        fields.append("timezone")
    if payload.approval_workflow_mode is not None:
        if payload.approval_workflow_mode not in Workspace.ApprovalWorkflowMode.values:
            raise HttpError(400, "Invalid approval workflow mode.")
        ws.approval_workflow_mode = payload.approval_workflow_mode
        fields.append("approval_workflow_mode")
    if payload.agent_autonomy is not None:
        if payload.agent_autonomy not in Workspace.AgentAutonomy.values:
            raise HttpError(400, "Invalid agent autonomy level.")
        ws.agent_autonomy = payload.agent_autonomy
        fields.append("agent_autonomy")
    if fields:
        ws.save(update_fields=[*fields, "updated_at"])
    return _workspace_payload(ws, m)


@router.post("/{workspace_id}/settings/icon", summary="Upload or remove the workspace logo")
def workspace_icon(
    request,
    workspace_id: uuid.UUID,
    icon: UploadedFile | None = File(None),  # noqa: B008
    remove: bool = Form(False),  # noqa: B008
):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers can change settings.")
    ws = m.workspace
    if remove:
        if ws.icon:
            ws.icon.delete(save=False)
            ws.icon = None
    elif icon is not None:
        try:
            ws_services.validate_icon(icon)
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        if ws.icon:
            ws.icon.delete(save=False)
        ws.icon = icon
    ws.save()
    return {"icon_url": ws.icon.url if ws.icon else ""}


@router.post("/{workspace_id}/settings/archive", summary="Archive the workspace")
def workspace_archive(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers can archive.")
    try:
        ws_services.archive_workspace(m.workspace)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"is_archived": True}


@router.post("/{workspace_id}/settings/unarchive", summary="Restore the workspace")
def workspace_unarchive(request, workspace_id: uuid.UUID):
    # ``scoped`` excludes archived workspaces, so look the membership up directly.
    m = (
        WorkspaceMembership.objects.select_related("workspace")
        .filter(user=request.user, workspace_id=workspace_id)  # type: ignore[misc]
        .first()
    )
    if m is None:
        raise HttpError(404, "Workspace not found")
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers can restore.")
    ws_services.unarchive_workspace(m.workspace)
    return {"is_archived": False}


@router.delete("/{workspace_id}/settings", summary="Delete the workspace permanently")
def workspace_delete(request, workspace_id: uuid.UUID):
    m = (
        WorkspaceMembership.objects.select_related("workspace", "workspace__organization")
        .filter(user=request.user, workspace_id=workspace_id)  # type: ignore[misc]
        .first()
    )
    if m is None:
        raise HttpError(404, "Workspace not found")
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers can delete.")
    try:
        name = ws_services.delete_workspace(m.workspace)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"deleted": name}


@router.get("/{workspace_id}/checklist", summary="Onboarding checklist for this user in this workspace")
def checklist(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    dismissed = OnboardingChecklist.objects.filter(user=request.user, workspace=m.workspace, is_dismissed=True).exists()
    items = [] if dismissed else get_checklist_items(m.workspace)
    done = sum(1 for i in items if i["completed"])
    return {
        "dismissed": dismissed or (bool(items) and done == len(items)),
        "completed": done,
        "total": len(items),
        "items": [
            {"key": i["key"], "title": i["title"], "description": i["description"], "completed": i["completed"]}
            for i in items
        ],
    }


@router.post("/{workspace_id}/checklist/dismiss", summary="Hide the checklist")
def checklist_dismiss(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    OnboardingChecklist.objects.update_or_create(
        user=request.user, workspace=m.workspace, defaults={"is_dismissed": True, "dismissed_at": timezone.now()}
    )
    return {"dismissed": True}


# ---------------------------------------------------------------------------
# Clients (client portal access)
# ---------------------------------------------------------------------------


def _client_invites(org, workspace) -> list[dict]:
    now = timezone.now()
    out = []
    for inv in (
        Invitation.objects.filter(organization=org, accepted_at__isnull=True, expires_at__gt=now)
        .select_related("invited_by")
        .order_by("-created_at")
    ):
        if any(
            str(a.get("workspace_id")) == str(workspace.id)
            and a.get("role") == WorkspaceMembership.WorkspaceRole.CLIENT
            for a in inv.workspace_assignments
        ):
            out.append(
                {
                    "id": str(inv.id),
                    "email": inv.email,
                    "invited_by": inv.invited_by.display_name if inv.invited_by else None,
                    "expires_at": inv.expires_at.isoformat(),
                }
            )
    return out


@router.get("/{workspace_id}/clients", summary="Client-portal users and pending client invitations")
def clients(request, workspace_id: uuid.UUID):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers manage clients.")
    ws = m.workspace
    now = timezone.now()
    tokens: dict = {}
    for tok in MagicLinkToken.objects.filter(workspace=ws, expires_at__gt=now).order_by("created_at"):
        tokens[tok.user_id] = tok
    rows = []
    for cm in (
        WorkspaceMembership.objects.filter(workspace=ws, workspace_role=WorkspaceMembership.WorkspaceRole.CLIENT)
        .select_related("user")
        .order_by("user__email")
    ):
        t: MagicLinkToken | None = tokens.get(cm.user_id)
        rows.append(
            {
                "membership_id": str(cm.id),
                "name": cm.user.display_name,
                "email": cm.user.email,
                "link_expires_at": t.expires_at.isoformat() if t else None,
                "link_last_used_at": t.last_used_at.isoformat() if t and t.last_used_at else None,
            }
        )
    return {"clients": rows, "pending_invites": _client_invites(ws.organization, ws)}


class Email(Schema):
    email: str


@router.post("/{workspace_id}/clients/invite", summary="Invite a client to the portal")
def client_invite(request, workspace_id: uuid.UUID, payload: Email):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers manage clients.")
    email = payload.email.strip()
    if not email:
        raise HttpError(400, "Email address is required.")
    try:
        member_services.create_invitation(
            org=m.workspace.organization,
            email=email,
            org_role=OrgMembership.OrgRole.MEMBER,
            workspace_assignments=[
                {"workspace_id": str(m.workspace.id), "role": WorkspaceMembership.WorkspaceRole.CLIENT}
            ],
            invited_by=request.user,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"pending_invites": _client_invites(m.workspace.organization, m.workspace)}


def _client_membership(m: WorkspaceMembership, membership_id) -> WorkspaceMembership:
    try:
        return WorkspaceMembership.objects.select_related("user").get(
            id=membership_id, workspace=m.workspace, workspace_role=WorkspaceMembership.WorkspaceRole.CLIENT
        )
    except WorkspaceMembership.DoesNotExist as exc:
        raise HttpError(404, "Client not found") from exc


@router.post("/{workspace_id}/clients/{uuid:membership_id}/send-link", summary="Email a fresh portal magic link")
def client_send_link(request, workspace_id: uuid.UUID, membership_id: uuid.UUID):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers manage clients.")
    cm = _client_membership(m, membership_id)
    try:
        token = portal_services.generate_magic_link(workspace=m.workspace, client_user=cm.user, created_by=request.user)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"link_expires_at": token.expires_at.isoformat()}


@router.delete("/{workspace_id}/clients/{uuid:membership_id}", summary="Remove a client from the workspace")
def client_remove(request, workspace_id: uuid.UUID, membership_id: uuid.UUID):
    m = scoped(request, workspace_id)
    if not _is_manager(m):
        raise HttpError(403, "Only workspace owners and managers manage clients.")
    cm = _client_membership(m, membership_id)
    MagicLinkToken.objects.filter(user=cm.user, workspace=m.workspace, expires_at__gt=timezone.now()).update(
        expires_at=timezone.now()
    )
    cm.delete()
    return {"removed": True}


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

org_router = Router(tags=["organization"])


def _org_payload(m: OrgMembership) -> dict:
    org = m.organization
    return {
        "id": str(org.id),
        "name": org.name,
        "default_timezone": org.default_timezone,
        "logo_url": org.logo_url,
        "role": m.org_role,
        "is_owner": m.org_role == OrgMembership.OrgRole.OWNER,
        "is_admin": m.org_role in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN),
        "deletion_requested_at": org.deletion_requested_at.isoformat() if org.deletion_requested_at else None,
        "deletion_scheduled_for": org.deletion_scheduled_for.isoformat() if org.deletion_scheduled_for else None,
        "timezones": sorted(available_timezones()),
    }


@org_router.get("/", summary="Organization settings")
def org_get(request):
    return _org_payload(_org_membership(request))


class OrgUpdate(Schema):
    name: str | None = None
    default_timezone: str | None = None


@org_router.patch("/", summary="Update organization name or default timezone")
def org_update(request, payload: OrgUpdate):
    m = _org_membership(request, "admin")
    try:
        if payload.name is not None:
            org_services.update_name(m.organization, payload.name)
        if payload.default_timezone is not None:
            org_services.update_timezone(m.organization, payload.default_timezone)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return _org_payload(m)


@org_router.post("/delete", summary="Schedule deletion in 14 days (owner only)")
def org_delete(request):
    m = _org_membership(request, "owner")
    org_services.schedule_deletion(m.organization)
    return _org_payload(m)


@org_router.post("/delete/cancel", summary="Cancel a pending deletion (owner only)")
def org_delete_cancel(request):
    m = _org_membership(request, "owner")
    org_services.cancel_deletion(m.organization)
    return _org_payload(m)


@org_router.post("/delete/now", summary="Delete immediately and sign out (owner only)")
def org_delete_now(request):
    m = _org_membership(request, "owner")
    org_services.delete_now(m.organization, request.user)
    logout(request)
    return {"deleted": True, "redirect": "/accounts/signup/"}


@org_router.get("/workspaces", summary="Every workspace in the organization with members")
def org_workspaces(request):
    m = _org_membership(request)
    rows = []
    for ws in (
        Workspace.objects.filter(organization=m.organization)
        .prefetch_related("memberships__user")
        .order_by("is_archived", "name")
    ):
        members = list(ws.memberships.all())
        mine = next((x for x in members if x.user_id == request.user.id), None)
        rows.append(
            {
                "id": str(ws.id),
                "name": ws.name,
                "is_archived": ws.is_archived,
                "member_count": len(members),
                "members": [{"name": x.user.display_name, "role": x.workspace_role} for x in members[:8]],
                "can_manage": bool(mine and _is_manager(mine)),
                "is_member": mine is not None,
            }
        )
    return {"workspaces": rows, "can_create": m.org_role in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN)}


class Name(Schema):
    name: str


@org_router.post("/workspaces", summary="Create a workspace (admin)")
def org_workspace_create(request, payload: Name):
    m = _org_membership(request, "admin")
    try:
        ws = ws_services.create_workspace(m.organization, request.user, payload.name)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"id": str(ws.id), "name": ws.name}


# ---------------------------------------------------------------------------
# Members and invitations
# ---------------------------------------------------------------------------


def _member_row(om: OrgMembership, ws_map: dict) -> dict:
    return {
        "membership_id": str(om.id),
        "user_id": str(om.user_id),
        "name": om.user.display_name,
        "email": om.user.email,
        "org_role": om.org_role,
        "joined_at": om.invited_at.isoformat() if om.invited_at else None,
        "workspaces": [
            {
                "id": str(wm.workspace_id),
                "name": wm.workspace.name,
                "role": wm.custom_role.name if wm.custom_role else wm.workspace_role,
            }
            for wm in ws_map.get(om.user_id, [])
        ],
    }


@org_router.get("/members", summary="Members, pending invitations, and what the caller may assign")
def members(request):
    m = _org_membership(request)
    org = m.organization
    is_admin = m.org_role in (OrgMembership.OrgRole.OWNER, OrgMembership.OrgRole.ADMIN)
    oms = list(OrgMembership.objects.filter(organization=org).select_related("user").order_by("invited_at"))
    workspaces = list(Workspace.objects.filter(organization=org, is_archived=False).order_by("name"))
    ws_map: dict = {}
    for wm in WorkspaceMembership.objects.filter(
        user_id__in=[o.user_id for o in oms], workspace_id__in=[w.id for w in workspaces]
    ).select_related("workspace", "custom_role"):
        ws_map.setdefault(wm.user_id, []).append(wm)
    invites = []
    if is_admin:
        invites = [
            {
                "id": str(i.id),
                "email": i.email,
                "org_role": i.org_role,
                "workspace_assignments": i.workspace_assignments,
                "invited_by": i.invited_by.display_name if i.invited_by else None,
                "expires_at": i.expires_at.isoformat(),
            }
            for i in Invitation.objects.filter(
                organization=org, accepted_at__isnull=True, expires_at__gt=timezone.now()
            )
            .select_related("invited_by")
            .order_by("-created_at")
        ]
    return {
        "members": [_member_row(o, ws_map) for o in oms],
        "pending_invites": invites,
        "workspaces": [{"id": str(w.id), "name": w.name} for w in workspaces],
        "org_role_choices": [{"value": v, "label": label} for v, label in _org_role_choices_for(m)],
        "workspace_role_choices": [
            {"value": v, "label": label} for v, label in WorkspaceMembership.WorkspaceRole.choices
        ],
        "is_admin": is_admin,
        "current_user_id": str(request.user.id),
    }


class Assignment(Schema):
    workspace_id: uuid.UUID
    role: str


class Invite(Schema):
    email: str
    org_role: str = OrgMembership.OrgRole.MEMBER
    workspaces: list[Assignment] = []


@org_router.post("/members/invite", summary="Invite a teammate (admin)")
def invite(request, payload: Invite):
    m = _org_membership(request, "admin")
    try:
        inv = member_services.create_invitation(
            org=m.organization,
            email=payload.email.strip(),
            org_role=payload.org_role,
            workspace_assignments=[{"workspace_id": str(a.workspace_id), "role": a.role} for a in payload.workspaces],
            invited_by=request.user,
            inviter=request.user,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"id": str(inv.id), "email": inv.email, "expires_at": inv.expires_at.isoformat()}


def _invitation(m: OrgMembership, invitation_id) -> Invitation:
    try:
        return Invitation.objects.get(id=invitation_id, organization=m.organization)
    except Invitation.DoesNotExist as exc:
        raise HttpError(404, "Invitation not found") from exc


@org_router.post("/members/invites/{uuid:invitation_id}/resend", summary="Resend an invitation (admin)")
def invite_resend(request, invitation_id: uuid.UUID):
    m = _org_membership(request, "admin")
    try:
        member_services.resend_invitation(_invitation(m, invitation_id))
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"resent": True}


@org_router.delete("/members/invites/{uuid:invitation_id}", summary="Revoke an invitation (admin)")
def invite_revoke(request, invitation_id: uuid.UUID):
    m = _org_membership(request, "admin")
    member_services.revoke_invitation(_invitation(m, invitation_id))
    return {"revoked": True}


def _membership(m: OrgMembership, membership_id) -> OrgMembership:
    try:
        return OrgMembership.objects.select_related("user").get(id=membership_id, organization=m.organization)
    except OrgMembership.DoesNotExist as exc:
        raise HttpError(404, "Member not found") from exc


class Role(Schema):
    org_role: str


@org_router.post("/members/{uuid:membership_id}/role", summary="Change a member's organization role (admin)")
def member_role(request, membership_id: uuid.UUID, payload: Role):
    m = _org_membership(request, "admin")
    target = _membership(m, membership_id)
    try:
        member_services.update_member_org_role(m.organization, target, payload.org_role, caller=request.user)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"org_role": target.org_role}


@org_router.delete("/members/{uuid:membership_id}", summary="Remove a member (admin)")
def member_remove(request, membership_id: uuid.UUID):
    m = _org_membership(request, "admin")
    target = _membership(m, membership_id)
    try:
        member_services.remove_member(m.organization, target, request.user)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"removed": True}


class Assignments(Schema):
    workspaces: list[Assignment]


@org_router.put("/members/{uuid:membership_id}/workspaces", summary="Set a member's workspace roles (admin)")
def member_workspaces(request, membership_id: uuid.UUID, payload: Assignments):
    m = _org_membership(request, "admin")
    target = _membership(m, membership_id)
    try:
        member_services.update_workspace_assignments(
            m.organization,
            target.user,
            [{"workspace_id": str(a.workspace_id), "role": a.role} for a in payload.workspaces],
            inviter=request.user,
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    wms = WorkspaceMembership.objects.filter(user=target.user, workspace__organization=m.organization).select_related(
        "workspace", "custom_role"
    )
    return {
        "workspaces": [{"id": str(w.workspace_id), "name": w.workspace.name, "role": w.workspace_role} for w in wms]
    }


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def _has_manage_keys(m: OrgMembership) -> bool:
    from apps.members.models import has_org_permission

    return has_org_permission(m, "manage_api_keys")


def _key_row(k: ApiKey) -> dict:
    now = timezone.now()
    status = "revoked" if k.revoked_at else ("expired" if k.expires_at and k.expires_at <= now else "active")
    return {
        "id": str(k.id),
        "name": k.name,
        "workspace_id": str(k.workspace_id),
        "workspace_name": k.workspace.name,
        "accounts": [
            {"id": str(a.id), "name": a.account_name, "platform": a.platform} for a in k.social_accounts.all()
        ],
        "permissions": list(k.permissions or []),
        "issued_by": k.issued_by.display_name if k.issued_by else None,
        "created_at": k.created_at.isoformat(),
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "status": status,
    }


@org_router.get("/api-keys", summary="Agent API keys across the organization")
def api_keys(request, show: str = ""):
    m = _org_membership(request)
    if not _has_manage_keys(m):
        raise HttpError(403, "Permission denied: manage_api_keys")
    qs = (
        ApiKey.objects.filter(workspace__organization=m.organization)
        .select_related("workspace", "issued_by")
        .prefetch_related("social_accounts")
        .order_by("-created_at")
    )
    if show != "all":
        qs = qs.filter(revoked_at__isnull=True)
    return {
        "keys": [_key_row(k) for k in qs],
        "revoked_count": ApiKey.objects.filter(
            workspace__organization=m.organization, revoked_at__isnull=False
        ).count(),
        "workspaces": [
            {"id": str(w.id), "name": w.name}
            for w in Workspace.objects.filter(organization=m.organization, is_archived=False).order_by("name")
        ],
    }


@org_router.get("/api-keys/options", summary="Accounts and grantable permissions for one workspace")
def api_key_options(request, workspace_id: uuid.UUID):
    m = _org_membership(request)
    if not _has_manage_keys(m):
        raise HttpError(403, "Permission denied: manage_api_keys")
    try:
        ws = Workspace.objects.get(id=workspace_id, organization=m.organization)
    except Workspace.DoesNotExist as exc:
        raise HttpError(404, "Workspace not found") from exc
    return {
        "accounts": [
            {"id": str(a.id), "name": a.account_name, "platform": a.platform}
            for a in SocialAccount.objects.filter(
                workspace=ws, connection_status=SocialAccount.ConnectionStatus.CONNECTED
            ).order_by("platform", "account_name")
        ],
        "permissions": [{"key": k, "label": label} for k, label in _grantable_permissions(request.user, ws)],
    }


def _expires(value: str | None):
    if not value:
        return None
    try:
        dt = parse_datetime(value)
        d = parse_date(value)
    except ValueError as exc:
        raise HttpError(400, "Could not parse expires_at.") from exc
    if dt is None and d is None:
        raise HttpError(400, "Could not parse expires_at.")
    if d is not None and dt is None:
        dt = datetime.combine(d, time.max)
    assert dt is not None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class IssueKey(Schema):
    name: str
    workspace_id: uuid.UUID
    social_account_ids: list[uuid.UUID]
    permissions: list[str]
    expires_at: str | None = None


def _accounts_in(ws, ids) -> list[SocialAccount]:
    accounts = list(SocialAccount.objects.filter(id__in=ids, workspace=ws))
    if len(accounts) != len(set(ids)):
        raise HttpError(400, "Some selected accounts do not belong to that workspace.")
    return accounts


@org_router.post("/api-keys", summary="Issue a key; the plaintext token is returned exactly once")
def api_key_issue(request, payload: IssueKey):
    m = _org_membership(request)
    if not _has_manage_keys(m):
        raise HttpError(403, "Permission denied: manage_api_keys")
    if not payload.name.strip():
        raise HttpError(400, "Name is required.")
    if not payload.social_account_ids:
        raise HttpError(400, "Select at least one connected account.")
    try:
        ws = Workspace.objects.get(id=payload.workspace_id, organization=m.organization)
    except Workspace.DoesNotExist as exc:
        raise HttpError(400, "Selected workspace is not in this organisation.") from exc
    accounts = _accounts_in(ws, payload.social_account_ids)
    try:
        issued = key_services.issue_api_key(
            workspace=ws,
            social_accounts=accounts,
            issued_by=request.user,
            name=payload.name.strip(),
            permissions=payload.permissions,
            expires_at=_expires(payload.expires_at),
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"key": _key_row(issued.api_key), "token": issued.plaintext_token}


def _key(m: OrgMembership, key_id) -> ApiKey:
    try:
        return ApiKey.objects.select_related("workspace").get(id=key_id, workspace__organization=m.organization)
    except ApiKey.DoesNotExist as exc:
        raise HttpError(404, "Key not found") from exc


class EditKey(Schema):
    social_account_ids: list[uuid.UUID]
    permissions: list[str]
    expires_at: str | None = None


@org_router.put("/api-keys/{uuid:key_id}", summary="Edit a key's scope")
def api_key_edit(request, key_id: uuid.UUID, payload: EditKey):
    m = _org_membership(request)
    if not _has_manage_keys(m):
        raise HttpError(403, "Permission denied: manage_api_keys")
    k = _key(m, key_id)
    if not k.is_active:
        raise HttpError(400, "This key is not active; it can't be edited.")
    if not payload.social_account_ids:
        raise HttpError(400, "Select at least one connected account.")
    accounts = _accounts_in(k.workspace, payload.social_account_ids)
    try:
        key_services.update_api_key(
            k,
            editor=request.user,
            permissions=payload.permissions,
            social_accounts=accounts,
            expires_at=_expires(payload.expires_at),
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    k.refresh_from_db()
    return _key_row(k)


@org_router.post("/api-keys/{uuid:key_id}/revoke", summary="Revoke a key")
def api_key_revoke(request, key_id: uuid.UUID):
    m = _org_membership(request)
    if not _has_manage_keys(m):
        raise HttpError(403, "Permission denied: manage_api_keys")
    k = _key(m, key_id)
    if k.revoked_at is None:
        key_services.revoke_api_key(k)
    return _key_row(k)
