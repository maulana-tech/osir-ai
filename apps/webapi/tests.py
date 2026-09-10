"""Browser session auth: the Next.js UI talks to both APIs with the Django session."""

from __future__ import annotations

import json
import secrets

import pytest
from django.test import Client

from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace


@pytest.fixture
def workspace(db, organization):
    return Workspace.objects.create(name="Main", organization=organization)


@pytest.fixture
def second_workspace(db, organization):
    return Workspace.objects.create(name="Other", organization=organization)


@pytest.fixture
def member_client(db, org_owner, workspace, second_workspace):
    for ws in (workspace, second_workspace):
        WorkspaceMembership.objects.create(
            user=org_owner, workspace=ws, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
        )
    client = Client(enforce_csrf_checks=True)
    client.force_login(org_owner)
    return client


def _csrf(client):
    """Plant a CSRF cookie the way the browser would have one, and return the matching header value."""
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    return token


@pytest.mark.django_db
class TestWebSession:
    def test_anonymous_is_401(self, client):
        assert client.get("/api/web/me/").status_code == 401
        assert client.get("/api/v1/me/").status_code == 401

    def test_me_lists_workspaces_and_current(self, member_client, org_owner, workspace, second_workspace):
        r = member_client.get("/api/web/me/")
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["email"] == org_owner.email
        assert {w["name"] for w in body["workspaces"]} >= {"Main", "Other"}  # plus the auto-provisioned default
        assert body["organization"]["can_create_workspace"] is True
        assert "create_posts" in body["workspaces"][0]["permissions"]

        r = member_client.get("/api/web/me/", HTTP_X_WORKSPACE_ID=str(second_workspace.id))
        assert r.json()["current_workspace_id"] == str(second_workspace.id)

    def test_agent_api_accepts_the_session(self, member_client, workspace):
        r = member_client.get("/api/v1/me/", HTTP_X_WORKSPACE_ID=str(workspace.id))
        assert r.status_code == 200
        assert r.json()["api_key_id"].startswith("session:")
        assert r.json()["workspace_id"] == str(workspace.id)

    def test_foreign_workspace_header_is_rejected(self, member_client, db, organization):
        other = Workspace.objects.create(name="Not mine", organization=organization)
        assert member_client.get("/api/web/me/", HTTP_X_WORKSPACE_ID=str(other.id)).status_code == 401

    def test_mutations_need_csrf(self, member_client, workspace):
        body = json.dumps({"workspace_id": str(workspace.id)})
        r = member_client.post("/api/web/me/workspace", data=body, content_type="application/json")
        assert r.status_code == 403
        token = _csrf(member_client)
        r = member_client.post(
            "/api/web/me/workspace", data=body, content_type="application/json", HTTP_X_CSRFTOKEN=token
        )
        assert r.status_code == 200
        member_client.get("/api/web/me/")  # refresh user row
        r = member_client.get("/api/web/me/")
        assert r.json()["current_workspace_id"] == str(workspace.id)

    def test_sidebar_scopes_to_membership(self, member_client, workspace, db, organization):
        r = member_client.get(f"/api/web/workspaces/{workspace.id}/sidebar")
        assert r.status_code == 200
        assert r.json()["channels"] == [] and r.json()["unread_inbox_count"] == 0
        other = Workspace.objects.create(name="Not mine", organization=organization)
        # RBACMiddleware rejects non-members of a URL workspace before the view runs.
        assert member_client.get(f"/api/web/workspaces/{other.id}/sidebar").status_code == 403

    def test_idempotency_key_requires_api_key(self, member_client, workspace):
        from apps.social_accounts.models import SocialAccount

        account = SocialAccount.objects.create(
            workspace=workspace, platform="linkedin_personal", account_platform_id="li", account_name="Me"
        )
        token = _csrf(member_client)
        r = member_client.post(
            "/api/v1/posts/",
            data=json.dumps({"social_account_id": str(account.id), "caption": "x", "idempotency_key": "k1"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_X_WORKSPACE_ID=str(workspace.id),
        )
        assert r.status_code == 400
        assert "Idempotency" in r.json()["detail"]


@pytest.mark.django_db
def test_rest_post_list_for_session(member_client, workspace):
    from apps.composer.services import create_post
    from apps.social_accounts.models import SocialAccount

    account = SocialAccount.objects.create(
        workspace=workspace, platform="linkedin_personal", account_platform_id="li", account_name="Me"
    )
    create_post(workspace=workspace, social_account=account, caption="hello")
    r = member_client.get("/api/v1/posts/?limit=10", HTTP_X_WORKSPACE_ID=str(workspace.id))
    assert r.status_code == 200
    body = r.json()
    assert [p["caption"] for p in body["posts"]] == ["hello"]
    assert body["next_cursor"] is None
    assert (
        member_client.get("/api/v1/posts/?status=published", HTTP_X_WORKSPACE_ID=str(workspace.id)).json()["posts"]
        == []
    )
