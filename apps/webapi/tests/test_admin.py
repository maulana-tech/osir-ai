"""Settings surfaces through the web API: channels, workspace, org, members, clients, keys, account."""

from __future__ import annotations

import json
import secrets
from unittest.mock import patch

import pytest

from apps.api_keys.models import ApiKey
from apps.members.models import Invitation, OrgMembership, WorkspaceMembership
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


def _send(client, method, path, data=None):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    kwargs = {"HTTP_X_CSRFTOKEN": token}
    if data is not None:
        kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(client, method)(path, **kwargs)


@pytest.fixture
def account(workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="facebook",
        account_platform_id="pg",
        account_name="Page",
        connection_status="connected",
    )


@pytest.mark.django_db
class TestChannels:
    def test_list_and_disconnect(self, member_client, workspace, account):
        body = member_client.get(f"/api/web/workspaces/{workspace.id}/channels").json()
        assert body["accounts"][0]["name"] == "Page" and body["can_manage"] is True
        assert any(p["platform"] == "facebook" for p in body["platforms"])
        with patch("apps.social_accounts.services.unsubscribe_account_webhooks"):
            r = _send(member_client, "post", f"/api/web/workspaces/{workspace.id}/channels/{account.id}/disconnect")
        assert r.status_code == 200 and r.json()["disconnected"] == "Page"
        assert not SocialAccount.objects.filter(id=account.id).exists()

    def test_retry_webhooks_requires_healthy_connection(self, member_client, workspace, account):
        SocialAccount.objects.filter(id=account.id).update(connection_status="error")
        r = _send(member_client, "post", f"/api/web/workspaces/{workspace.id}/channels/{account.id}/retry-webhooks")
        assert r.status_code == 400 and "Reconnect" in r.json()["detail"]


@pytest.mark.django_db
class TestWorkspaceSettings:
    def test_read_update_archive_delete(self, member_client, workspace, second_workspace):
        base = f"/api/web/workspaces/{workspace.id}/settings"
        body = member_client.get(base).json()
        assert body["name"] == "Main" and body["can_archive"] is True
        r = _send(
            member_client, "patch", base, {"name": "Renamed", "timezone": "Asia/Jakarta", "agent_autonomy": "autopilot"}
        )
        assert (
            r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["effective_timezone"] == "Asia/Jakarta"
        )
        assert _send(member_client, "patch", base, {"timezone": "Mars/Olympus"}).status_code == 400
        assert _send(member_client, "patch", base, {"agent_autonomy": "bogus"}).status_code == 400
        assert _send(member_client, "patch", base, {"approval_workflow_mode": "bogus"}).status_code == 400
        workspace.refresh_from_db()
        assert workspace.agent_autonomy == "autopilot"
        assert _send(member_client, "post", f"{base}/archive").status_code == 200
        workspace.refresh_from_db()
        assert workspace.is_archived is True
        assert _send(member_client, "post", f"{base}/unarchive").status_code == 200
        assert _send(member_client, "delete", base).status_code == 200
        assert not Workspace.objects.filter(id=workspace.id).exists()

    def test_checklist(self, member_client, workspace):
        body = member_client.get(f"/api/web/workspaces/{workspace.id}/checklist").json()
        assert body["total"] > 0 and body["dismissed"] is False
        _send(member_client, "post", f"/api/web/workspaces/{workspace.id}/checklist/dismiss")
        assert member_client.get(f"/api/web/workspaces/{workspace.id}/checklist").json()["dismissed"] is True


@pytest.mark.django_db
class TestOrgAndMembers:
    def test_org_settings(self, member_client, organization):
        body = member_client.get("/api/web/org/").json()
        assert body["is_owner"] is True
        r = _send(member_client, "patch", "/api/web/org/", {"name": "Acme", "default_timezone": "Europe/Berlin"})
        assert r.json()["name"] == "Acme" and r.json()["default_timezone"] == "Europe/Berlin"
        assert _send(member_client, "patch", "/api/web/org/", {"default_timezone": "Nope/Nope"}).status_code == 400
        r = _send(member_client, "post", "/api/web/org/delete")
        assert r.json()["deletion_scheduled_for"]
        assert _send(member_client, "post", "/api/web/org/delete/cancel").json()["deletion_scheduled_for"] is None

    def test_workspaces_and_create(self, member_client, workspace):
        body = member_client.get("/api/web/org/workspaces").json()
        assert body["can_create"] is True and any(w["name"] == "Main" for w in body["workspaces"])
        r = _send(member_client, "post", "/api/web/org/workspaces", {"name": "Fresh"})
        assert r.status_code == 200
        assert WorkspaceMembership.objects.filter(workspace_id=r.json()["id"], workspace_role="owner").exists()

    def test_members_invite_role_remove(self, member_client, org_owner, workspace, organization):
        body = member_client.get("/api/web/org/members").json()
        assert body["is_admin"] is True and body["members"][0]["email"] == org_owner.email
        with patch("apps.members.services._send_invite_email"):
            r = _send(
                member_client,
                "post",
                "/api/web/org/members/invite",
                {
                    "email": "new@example.com",
                    "org_role": "member",
                    "workspaces": [{"workspace_id": str(workspace.id), "role": "editor"}],
                },
            )
        assert r.status_code == 200, r.content
        inv_id = r.json()["id"]
        assert Invitation.objects.filter(id=inv_id).exists()
        assert _send(member_client, "delete", f"/api/web/org/members/invites/{inv_id}").status_code == 200

        from apps.accounts.models import User

        other = User.objects.create_user(email="other@example.com", password="x", name="Other")
        om = OrgMembership.objects.create(user=other, organization=organization, org_role="member")
        r = _send(
            member_client,
            "put",
            f"/api/web/org/members/{om.id}/workspaces",
            {"workspaces": [{"workspace_id": str(workspace.id), "role": "viewer"}]},
        )
        assert r.status_code == 200 and r.json()["workspaces"][0]["role"] == "viewer"
        assert _send(member_client, "delete", f"/api/web/org/members/{om.id}").status_code == 200
        assert not OrgMembership.objects.filter(id=om.id).exists()


@pytest.mark.django_db
class TestApiKeys:
    def test_issue_edit_revoke(self, member_client, workspace, account):
        opts = member_client.get(f"/api/web/org/api-keys/options?workspace_id={workspace.id}").json()
        assert opts["accounts"][0]["id"] == str(account.id) and "create_posts" in [
            p["key"] for p in opts["permissions"]
        ]
        r = _send(
            member_client,
            "post",
            "/api/web/org/api-keys",
            {
                "name": "bot",
                "workspace_id": str(workspace.id),
                "social_account_ids": [str(account.id)],
                "permissions": ["create_posts"],
            },
        )
        assert r.status_code == 200, r.content
        assert r.json()["token"].startswith("bb_studio_")
        key_id = r.json()["key"]["id"]
        r = _send(
            member_client,
            "put",
            f"/api/web/org/api-keys/{key_id}",
            {"social_account_ids": [str(account.id)], "permissions": ["create_posts", "view_analytics"]},
        )
        assert r.status_code == 200 and "view_analytics" in r.json()["permissions"]
        assert _send(member_client, "post", f"/api/web/org/api-keys/{key_id}/revoke").json()["status"] == "revoked"
        assert ApiKey.objects.get(id=key_id).revoked_at is not None
        assert member_client.get("/api/web/org/api-keys").json()["keys"] == []
        assert len(member_client.get("/api/web/org/api-keys?show=all").json()["keys"]) == 1


@pytest.mark.django_db
class TestAccountAndNotifications:
    def test_profile_password_preferences(self, member_client, org_owner):
        body = member_client.get("/api/web/me/account").json()
        assert body["email"] == org_owner.email and body["sole_owner_of"]
        assert _send(member_client, "patch", "/api/web/me/account", {"name": "Neo"}).json()["name"] == "Neo"
        r = _send(
            member_client,
            "post",
            "/api/web/me/account/password",
            {"current_password": "wrong", "password": "longenough1", "password_confirm": "longenough1"},
        )
        assert r.status_code == 400
        r = _send(member_client, "delete", "/api/web/me/account")
        assert r.status_code == 400 and "sole owner" in r.json()["detail"]

        prefs = member_client.get("/api/web/me/notification-preferences").json()
        row = prefs["matrix"][0]
        r = _send(
            member_client,
            "put",
            "/api/web/me/notification-preferences",
            {
                "toggles": [{"event_type": row["event_type"], "channel": "email", "enabled": True}],
                "quiet_hours": {
                    "is_enabled": True,
                    "start_time": "22:00",
                    "end_time": "07:00",
                    "timezone": "Asia/Jakarta",
                    "digest_mode": True,
                },
            },
        )
        assert r.status_code == 200, r.content
        assert r.json()["quiet_hours"]["start_time"] == "22:00"
        saved_row = next(m for m in r.json()["matrix"] if m["event_type"] == row["event_type"])
        assert next(c for c in saved_row["channels"] if c["channel"] == "email")["enabled"] is True

    def test_notifications_list_and_read(self, member_client, org_owner):
        from apps.notifications.models import Notification

        n = Notification.objects.create(user=org_owner, event_type="post_approved", title="Approved")
        body = member_client.get("/api/web/me/notifications").json()
        assert body["unread_count"] == 1 and body["notifications"][0]["id"] == str(n.id)
        _send(member_client, "post", f"/api/web/me/notifications/{n.id}/read")
        assert member_client.get("/api/web/me/notifications?read_status=unread").json()["notifications"] == []
        Notification.objects.create(user=org_owner, event_type="post_failed", title="Failed")
        assert _send(member_client, "post", "/api/web/me/notifications/read-all").json()["marked"] == 1
        assert member_client.get("/api/web/me/notifications").json()["unread_count"] == 0

    def test_notifications_filter_by_event_type(self, member_client, org_owner):
        from apps.notifications.models import Notification

        Notification.objects.create(user=org_owner, event_type="post_approved", title="Approved")
        Notification.objects.create(user=org_owner, event_type="post_failed", title="Failed")
        body = member_client.get("/api/web/me/notifications?event_type=post_approved").json()
        assert [n["title"] for n in body["notifications"]] == ["Approved"] and body["total"] == 1
        assert {e["value"] for e in body["event_types"]} >= {"post_approved", "post_failed"}

    def test_notification_preferences_matrix_covers_every_event_and_channel(self, member_client):
        from apps.notifications.models import Channel, EventType

        body = member_client.get("/api/web/me/notification-preferences").json()
        assert {m["event_type"] for m in body["matrix"]} == set(EventType.values)
        assert all({c["channel"] for c in m["channels"]} == set(Channel.values) for m in body["matrix"])
        assert body["quiet_hours"]["timezone"]
