"""API-key issuance rules through the web API (ported from the retired Django views)."""

from __future__ import annotations

import json
import secrets

import pytest
from django.test import Client

from apps.accounts.models import User
from apps.api_keys import services
from apps.api_keys.models import ApiKey
from apps.members.models import PERMISSION_KEYS, OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

ISSUE = "/api/web/org/api-keys"


def _send(client, method, path, data=None):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    kwargs = {"HTTP_X_CSRFTOKEN": token}
    if data is not None:
        kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(client, method)(path, **kwargs)


def _account(workspace, name="LinkedIn UI", status=SocialAccount.ConnectionStatus.CONNECTED, pid=None):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id=pid or f"li-{name}",
        account_name=name,
        connection_status=status,
    )


@pytest.fixture
def account(workspace):
    return _account(workspace)


def _issue_payload(workspace, account, **extra):
    return {
        "name": "test bot",
        "workspace_id": str(workspace.id),
        "social_account_ids": [str(account.id)],
        "permissions": ["create_posts"],
        **extra,
    }


@pytest.mark.django_db
class TestOptions:
    def test_returns_connected_accounts_only(self, member_client, workspace, account):
        broken = _account(workspace, "Broken", SocialAccount.ConnectionStatus.DISCONNECTED)
        body = member_client.get(f"{ISSUE}/options?workspace_id={workspace.id}").json()
        ids = {a["id"] for a in body["accounts"]}
        assert str(account.id) in ids and str(broken.id) not in ids

    def test_foreign_workspace_is_not_found(self, member_client):
        foreign = Workspace.objects.create(name="Foreign", organization=Organization.objects.create(name="Other"))
        assert member_client.get(f"{ISSUE}/options?workspace_id={foreign.id}").status_code == 404

    def test_malformed_workspace_id_is_422_not_500(self, member_client):
        assert member_client.get(f"{ISSUE}/options?workspace_id=not-a-uuid").status_code == 422

    def test_permissions_intersected_with_issuer(self, member_client, workspace, organization):
        # The org owner (a workspace owner) is offered every permission …
        keys = {
            p["key"] for p in member_client.get(f"{ISSUE}/options?workspace_id={workspace.id}").json()["permissions"]
        }
        assert keys == set(PERMISSION_KEYS)
        # … an org admin who is only an editor in the workspace is offered the editor's set.
        editor = User.objects.create_user(email="editor@example.com", password="x", name="Ed")
        OrgMembership.objects.filter(user=editor).exclude(organization=organization).delete()
        OrgMembership.objects.create(user=editor, organization=organization, org_role=OrgMembership.OrgRole.ADMIN)
        wm = WorkspaceMembership.objects.create(
            user=editor, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.EDITOR
        )
        c = Client()
        c.force_login(editor)
        keys = {p["key"] for p in c.get(f"{ISSUE}/options?workspace_id={workspace.id}").json()["permissions"]}
        assert keys == {k for k, v in wm.effective_permissions.items() if v}
        assert "publish_directly" not in keys

    def test_member_without_manage_api_keys_is_forbidden(self, member_client, organization, workspace):
        member = User.objects.create_user(email="member@example.com", password="x", name="M")
        OrgMembership.objects.filter(user=member).exclude(organization=organization).delete()
        OrgMembership.objects.create(user=member, organization=organization, org_role=OrgMembership.OrgRole.MEMBER)
        WorkspaceMembership.objects.create(
            user=member, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.VIEWER
        )
        c = Client()
        c.force_login(member)
        assert c.get(ISSUE).status_code == 403
        assert c.get(f"{ISSUE}/options?workspace_id={workspace.id}").status_code == 403


@pytest.mark.django_db
class TestIssue:
    def test_happy_path_reveals_token_once(self, member_client, workspace, account):
        r = _send(member_client, "post", ISSUE, _issue_payload(workspace, account))
        assert r.status_code == 200, r.content
        assert r.json()["token"].startswith("bb_studio_")
        key = ApiKey.objects.get(workspace=workspace)
        assert key.name == "test bot" and "create_posts" in key.permissions
        # The list never carries the plaintext token again.
        assert "bb_studio_" not in member_client.get(ISSUE).content.decode()

    def test_missing_name_is_rejected(self, member_client, workspace, account):
        r = _send(member_client, "post", ISSUE, _issue_payload(workspace, account, name="  "))
        assert r.status_code == 400 and "Name is required" in r.json()["detail"]
        assert ApiKey.objects.count() == 0

    def test_empty_accounts_are_rejected(self, member_client, workspace, account):
        r = _send(member_client, "post", ISSUE, _issue_payload(workspace, account, social_account_ids=[]))
        assert r.status_code == 400 and "at least one" in r.json()["detail"]
        assert ApiKey.objects.count() == 0

    def test_foreign_workspace_is_rejected(self, member_client, account):
        foreign = Workspace.objects.create(name="Foreign", organization=Organization.objects.create(name="Other"))
        r = _send(member_client, "post", ISSUE, _issue_payload(foreign, account))
        assert r.status_code == 400 and "not in this organisation" in r.json()["detail"]
        assert ApiKey.objects.count() == 0

    def test_account_outside_workspace_is_rejected(self, member_client, workspace, second_workspace):
        foreign_sa = _account(second_workspace, "Foreign LinkedIn")
        r = _send(member_client, "post", ISSUE, _issue_payload(workspace, foreign_sa))
        assert r.status_code == 400 and "do not belong to that workspace" in r.json()["detail"]
        assert ApiKey.objects.count() == 0

    def test_malformed_account_id_is_422_not_500(self, member_client, workspace, account):
        r = _send(member_client, "post", ISSUE, _issue_payload(workspace, account, social_account_ids=["not-a-uuid"]))
        assert r.status_code == 422
        assert ApiKey.objects.count() == 0

    def test_permissions_beyond_issuer_are_rejected(self, member_client, workspace, account, organization):
        editor = User.objects.create_user(email="editor@example.com", password="x", name="Ed")
        OrgMembership.objects.filter(user=editor).exclude(organization=organization).delete()
        OrgMembership.objects.create(user=editor, organization=organization, org_role=OrgMembership.OrgRole.ADMIN)
        WorkspaceMembership.objects.create(
            user=editor, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.EDITOR
        )
        c = Client()
        c.force_login(editor)
        r = _send(c, "post", ISSUE, _issue_payload(workspace, account, permissions=["publish_directly"]))
        assert r.status_code == 400
        assert ApiKey.objects.count() == 0


@pytest.mark.django_db
class TestEditAndRevoke:
    def _issue(self, org_owner, workspace, account, permissions=("create_posts",)):
        return services.issue_api_key(
            workspace=workspace,
            social_accounts=[account],
            issued_by=org_owner,
            name="editable",
            permissions=list(permissions),
        ).api_key

    def test_edit_updates_permissions_accounts_and_expiry(self, member_client, org_owner, workspace, account):
        second = _account(workspace, "Second UI")
        key = self._issue(org_owner, workspace, account)
        r = _send(
            member_client,
            "put",
            f"{ISSUE}/{key.id}",
            {"permissions": ["approve_posts"], "social_account_ids": [str(second.id)], "expires_at": "2030-01-01"},
        )
        assert r.status_code == 200, r.content
        key.refresh_from_db()
        assert key.permissions == ["approve_posts"]
        assert set(key.social_accounts.values_list("id", flat=True)) == {second.id}
        assert key.expires_at is not None and key.expires_at.year == 2030

    def test_edit_with_empty_permissions_clears_them(self, member_client, org_owner, workspace, account):
        key = self._issue(org_owner, workspace, account)
        r = _send(
            member_client, "put", f"{ISSUE}/{key.id}", {"permissions": [], "social_account_ids": [str(account.id)]}
        )
        assert r.status_code == 200
        key.refresh_from_db()
        assert key.permissions == []

    def test_edit_rejects_empty_accounts_and_foreign_accounts(
        self, member_client, org_owner, workspace, second_workspace, account
    ):
        key = self._issue(org_owner, workspace, account)
        r = _send(
            member_client, "put", f"{ISSUE}/{key.id}", {"permissions": ["create_posts"], "social_account_ids": []}
        )
        assert r.status_code == 400 and "at least one" in r.json()["detail"]
        foreign_sa = _account(second_workspace, "Foreign")
        r = _send(
            member_client,
            "put",
            f"{ISSUE}/{key.id}",
            {"permissions": ["create_posts"], "social_account_ids": [str(foreign_sa.id)]},
        )
        assert r.status_code == 400 and "do not belong" in r.json()["detail"]
        key.refresh_from_db()
        assert key.permissions == ["create_posts"]
        assert set(key.social_accounts.values_list("id", flat=True)) == {account.id}

    def test_inactive_key_cannot_be_edited(self, member_client, org_owner, workspace, account):
        key = self._issue(org_owner, workspace, account)
        services.revoke_api_key(key)
        r = _send(
            member_client, "put", f"{ISSUE}/{key.id}", {"permissions": [], "social_account_ids": [str(account.id)]}
        )
        assert r.status_code == 400 and "not active" in r.json()["detail"]
        key.refresh_from_db()
        assert key.permissions == ["create_posts"]

    def test_foreign_org_key_is_not_found(self, member_client):
        other_org = Organization.objects.create(name="Other")
        foreign_ws = Workspace.objects.create(name="Foreign", organization=other_org)
        foreign_user = User.objects.create_user(email="foreign@example.com", password="x", name="F")
        OrgMembership.objects.create(user=foreign_user, organization=other_org, org_role=OrgMembership.OrgRole.OWNER)
        WorkspaceMembership.objects.create(
            user=foreign_user, workspace=foreign_ws, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
        )
        foreign_sa = _account(foreign_ws, "Other LinkedIn")
        key = services.issue_api_key(
            workspace=foreign_ws, social_accounts=[foreign_sa], issued_by=foreign_user, name="k", permissions=[]
        ).api_key
        assert _send(member_client, "post", f"{ISSUE}/{key.id}/revoke").status_code == 404
        r = _send(
            member_client, "put", f"{ISSUE}/{key.id}", {"permissions": [], "social_account_ids": [str(foreign_sa.id)]}
        )
        assert r.status_code == 404
        key.refresh_from_db()
        assert key.revoked_at is None

    def test_revoke_flips_revoked_at(self, member_client, org_owner, workspace, account):
        key = self._issue(org_owner, workspace, account)
        r = _send(member_client, "post", f"{ISSUE}/{key.id}/revoke")
        assert r.status_code == 200 and r.json()["status"] == "revoked"
        key.refresh_from_db()
        assert key.revoked_at is not None
