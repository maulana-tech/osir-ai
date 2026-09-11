"""Invite / role-hierarchy enforcement through the web API (ported from the retired Django views).

An org admin must not be able to invite users with org/workspace roles above
their own, nor demote an org owner; only owners are offered the Admin role.
"""

from __future__ import annotations

import json
import secrets
from unittest.mock import patch

import pytest
from django.test import Client

from apps.accounts.models import User
from apps.members.models import Invitation, OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace

INVITE = "/api/web/org/members/invite"


def _send(client, method, path, data=None):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    kwargs = {"HTTP_X_CSRFTOKEN": token}
    if data is not None:
        kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(client, method)(path, **kwargs)


def _user(email, org, org_role, workspace=None, workspace_role=None):
    """A user whose only org is ``org`` (the signup signal's auto-org is dropped)."""
    user = User.objects.create_user(email=email, password="testpass123")
    auto_orgs = list(OrgMembership.objects.filter(user=user).values_list("organization_id", flat=True))
    WorkspaceMembership.objects.filter(user=user).delete()
    OrgMembership.objects.filter(user=user).delete()
    Organization.objects.filter(id__in=auto_orgs).delete()
    OrgMembership.objects.create(user=user, organization=org, org_role=org_role)
    if workspace is not None:
        WorkspaceMembership.objects.create(user=user, workspace=workspace, workspace_role=workspace_role)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return user, client


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def ws_a(org):
    return Workspace.objects.create(organization=org, name="WS-A")


@pytest.fixture
def ws_b(org):
    return Workspace.objects.create(organization=org, name="WS-B")


@pytest.fixture
def owner(org, ws_a):
    return _user("owner@example.com", org, "owner", ws_a, "owner")


@pytest.fixture
def admin(org, ws_a):
    # Admin is a viewer in WS-A (cannot grant owner there) and not a member of WS-B.
    return _user("admin@example.com", org, "admin", ws_a, "viewer")


def _invite(client, email, org_role, workspace=None, role=None):
    payload = {"email": email, "org_role": org_role, "workspaces": []}
    if workspace is not None:
        payload["workspaces"] = [{"workspace_id": str(workspace.id), "role": role}]
    with patch("apps.members.services._send_invite_email"):
        return _send(client, "post", INVITE, payload)


@pytest.mark.django_db
class TestInviteRoleHierarchy:
    def test_admin_cannot_invite_as_owner_of_workspace_they_only_view(self, admin, ws_a):
        assert _invite(admin[1], "victim@example.com", "member", ws_a, "owner").status_code == 400
        assert not Invitation.objects.filter(email="victim@example.com").exists()

    def test_admin_cannot_invite_into_workspace_they_dont_belong_to(self, admin, ws_b):
        assert _invite(admin[1], "victim@example.com", "member", ws_b, "viewer").status_code == 400
        assert not Invitation.objects.filter(email="victim@example.com").exists()

    def test_admin_cannot_invite_as_admin(self, admin):
        assert _invite(admin[1], "lateral@example.com", "admin").status_code == 400
        assert not Invitation.objects.filter(email="lateral@example.com").exists()

    def test_owner_can_invite_admin_with_any_workspace_role(self, owner, ws_a):
        assert _invite(owner[1], "legit@example.com", "admin", ws_a, "owner").status_code == 200
        assert Invitation.objects.filter(email="legit@example.com").exists()

    def test_admin_with_manager_role_can_invite_editor(self, admin, ws_b):
        WorkspaceMembership.objects.create(user=admin[0], workspace=ws_b, workspace_role="manager")
        assert _invite(admin[1], "editor@example.com", "member", ws_b, "editor").status_code == 200
        assert Invitation.objects.filter(email="editor@example.com").exists()


@pytest.mark.django_db
class TestOrgRoleChoiceGating:
    """Only owners are offered the Admin org role (services enforce it; the UI must not offer it)."""

    def test_admin_is_not_offered_the_admin_role(self, admin):
        body = admin[1].get("/api/web/org/members").json()
        assert [c["value"] for c in body["org_role_choices"]] == ["member"]

    def test_owner_is_offered_the_admin_role(self, owner):
        body = owner[1].get("/api/web/org/members").json()
        assert [c["value"] for c in body["org_role_choices"]] == ["admin", "member"]

    def test_members_payload_lists_workspaces_and_unique_members(self, owner, org, ws_a, ws_b):
        for i in range(2):
            _user(f"member-{i}@example.com", org, "member")
        body = owner[1].get("/api/web/org/members").json()
        ids = [m["membership_id"] for m in body["members"]]
        assert len(ids) == 3 and len(set(ids)) == 3
        assert {w["name"] for w in body["workspaces"]} == {"WS-A", "WS-B"}


@pytest.mark.django_db
class TestUpdateMemberRoleHierarchy:
    def test_admin_cannot_demote_owner(self, admin, org):
        other_owner, _ = _user("owner2@example.com", org, "owner")
        om = OrgMembership.objects.get(user=other_owner)
        r = _send(admin[1], "post", f"/api/web/org/members/{om.id}/role", {"org_role": "admin"})
        assert r.status_code == 400
        om.refresh_from_db()
        assert om.org_role == "owner"

    def test_admin_cannot_promote_member_to_admin(self, admin, org):
        member, _ = _user("member@example.com", org, "member")
        om = OrgMembership.objects.get(user=member)
        r = _send(admin[1], "post", f"/api/web/org/members/{om.id}/role", {"org_role": "admin"})
        assert r.status_code == 400
        om.refresh_from_db()
        assert om.org_role == "member"


@pytest.mark.django_db
class TestManageWorkspacesExistingRole:
    """The caller must outrank the *current* workspace role too, otherwise a viewer-level
    admin could silently demote (or remove) a workspace owner."""

    @pytest.fixture
    def victim(self, org, ws_a):
        user, _ = _user("victim@example.com", org, "member", ws_a, "owner")
        return OrgMembership.objects.get(user=user), WorkspaceMembership.objects.get(user=user)

    def _put(self, client, om, assignments):
        return _send(client, "put", f"/api/web/org/members/{om.id}/workspaces", {"workspaces": assignments})

    def test_viewer_level_admin_cannot_demote_owner(self, admin, ws_a, victim):
        om, wm = victim
        assert self._put(admin[1], om, [{"workspace_id": str(ws_a.id), "role": "viewer"}]).status_code == 400
        wm.refresh_from_db()
        assert wm.workspace_role == "owner"

    def test_viewer_level_admin_cannot_remove_owner(self, admin, victim):
        om, wm = victim
        assert self._put(admin[1], om, []).status_code == 400
        assert WorkspaceMembership.objects.filter(id=wm.id).exists()

    def test_admin_who_is_also_owner_can_change_owner_to_viewer(self, admin, ws_a, victim):
        WorkspaceMembership.objects.filter(user=admin[0], workspace=ws_a).update(workspace_role="owner")
        om, wm = victim
        assert self._put(admin[1], om, [{"workspace_id": str(ws_a.id), "role": "viewer"}]).status_code == 200
        wm.refresh_from_db()
        assert wm.workspace_role == "viewer"


@pytest.mark.django_db
def test_workspace_manager_can_invite_client(org, ws_a):
    """A workspace manager who is only org-role=member must still be able to invite clients."""
    _, client = _user("manager@example.com", org, "member", ws_a, "manager")
    with patch("apps.members.services._send_invite_email"):
        r = _send(client, "post", f"/api/web/workspaces/{ws_a.id}/clients/invite", {"email": "newclient@example.com"})
    assert r.status_code == 200, r.content
    inv = Invitation.objects.get(email="newclient@example.com")
    assert inv.workspace_assignments == [{"workspace_id": str(ws_a.id), "role": "client"}]
