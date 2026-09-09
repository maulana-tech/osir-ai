"""Composio fallback: offered only when the org has no developer app, and the
resulting account is proxy-backed with no tokens of its own."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.social_accounts.models import SocialAccount
from apps.social_accounts.views import COMPOSIO_SESSION_KEY
from providers.types import AccountProfile

COMPOSIO = {
    "COMPOSIO_API_KEY": "ck",
    "COMPOSIO_AUTH_CONFIGS": {"linkedin_personal": "ac_li", "facebook": "ac_fb"},
    "PLATFORM_CREDENTIALS_FROM_ENV": {},
}


@pytest.fixture(autouse=True)
def _composio_settings(settings):
    for key, value in COMPOSIO.items():
        setattr(settings, key, value)


@pytest.fixture
def workspace(db, organization):
    from apps.workspaces.models import Workspace

    return Workspace.objects.create(name="WS", organization=organization)


@pytest.fixture
def owner_client(client, org_owner, workspace):
    from apps.members.models import WorkspaceMembership

    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client.force_login(org_owner)
    return client


@pytest.mark.django_db
class TestComposioFallback:
    def test_grid_offers_composio_only_where_no_own_credentials(self, owner_client, workspace):
        r = owner_client.get(reverse("social_accounts:connect", kwargs={"workspace_id": workspace.id}))
        assert r.context["composio_platforms"] == {"linkedin_personal", "facebook"}
        assert b"Connect via Composio" in r.content

    def test_own_credentials_win(self, owner_client, workspace, organization):
        from apps.credentials.models import PlatformCredential

        PlatformCredential.objects.create(
            organization=organization,
            platform="linkedin_personal",
            credentials={"client_id": "own", "client_secret": "own"},
            is_configured=True,
        )
        r = owner_client.get(reverse("social_accounts:connect", kwargs={"workspace_id": workspace.id}))
        assert r.context["composio_platforms"] == {"facebook"}

    def test_connect_redirects_to_composio_and_callback_creates_proxy_account(self, owner_client, workspace):
        url = reverse("social_accounts:connect", kwargs={"workspace_id": workspace.id})
        with patch(
            "apps.credentials.composio.create_link", return_value=("ca_123", "https://connect.composio.dev/x")
        ) as link:
            r = owner_client.post(url, {"platform": "linkedin_personal"})
        assert r.status_code == 302 and r["Location"] == "https://connect.composio.dev/x"
        assert link.call_args.kwargs["platform"] == "linkedin_personal"
        assert link.call_args.kwargs["callback_url"].endswith("/social-accounts/composio/callback/")
        assert owner_client.session[COMPOSIO_SESSION_KEY]["connected_account_id"] == "ca_123"

        profile = AccountProfile(platform_id="li-1", name="Ada", handle="ada", avatar_url="", follower_count=5)
        with (
            patch("apps.credentials.composio.connection_status", return_value="ACTIVE"),
            patch("providers.linkedin_personal.LinkedInPersonalProvider.get_profile", return_value=profile) as gp,
            patch("apps.social_accounts.views.subscribe_account_webhooks_task"),
        ):
            r = owner_client.get(
                reverse("social_accounts:composio_callback") + "?connected_account_id=ca_123&status=success"
            )
        assert r.status_code == 302
        gp.assert_called_once_with("")
        account = SocialAccount.objects.get(workspace=workspace, platform="linkedin_personal")
        assert account.auth_source == SocialAccount.AuthSource.COMPOSIO
        assert account.composio_connected_account_id == "ca_123"
        assert account.oauth_access_token == ""

    def test_callback_rejects_unfinished_connection(self, owner_client, workspace):
        session = owner_client.session
        session[COMPOSIO_SESSION_KEY] = {
            "workspace_id": str(workspace.id),
            "platform": "linkedin_personal",
            "user_id": str(owner_client.session["_auth_user_id"]),
            "connected_account_id": "ca_9",
        }
        session.save()
        with patch("apps.credentials.composio.connection_status", return_value="INITIATED"):
            r = owner_client.get(reverse("social_accounts:composio_callback"))
        assert r.status_code == 302
        assert not SocialAccount.objects.filter(workspace=workspace).exists()

    def test_publish_credentials_carry_proxy_for_composio_accounts(self, workspace):
        from apps.publisher.engine import _resolve_publish_credentials

        account = SocialAccount.objects.create(
            workspace=workspace,
            platform="linkedin_personal",
            account_platform_id="li-1",
            account_name="Ada",
            auth_source=SocialAccount.AuthSource.COMPOSIO,
            composio_connected_account_id="ca_123",
        )
        creds = _resolve_publish_credentials(account)
        assert creds["composio_connected_account_id"] == "ca_123"
        assert creds["composio_api_key"] == "ck"
