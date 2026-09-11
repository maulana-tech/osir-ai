"""Analytics through the web API: account list, unavailable platforms, and a fresh account."""

from __future__ import annotations

import pytest

from apps.social_accounts.models import AnalyticsPlatformConfig, SocialAccount


@pytest.fixture
def accounts(workspace):
    yt = SocialAccount.objects.create(
        workspace=workspace,
        platform="youtube",
        account_platform_id="yt",
        account_name="Tube",
        connection_status="connected",
    )
    li = SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id="li",
        account_name="Me",
        connection_status="connected",
    )
    return yt, li


@pytest.mark.django_db
class TestAnalytics:
    def test_index_prefers_an_account_with_analytics(self, member_client, workspace, accounts):
        yt, li = accounts
        body = member_client.get(f"/api/web/workspaces/{workspace.id}/analytics").json()
        by_id = {a["id"]: a for a in body["accounts"]}
        assert by_id[str(li.id)]["analytics_available"] is False
        assert by_id[str(li.id)]["unavailable_reason"]
        if AnalyticsPlatformConfig.enabled_platforms():
            assert body["preferred_account_id"] == str(yt.id)

    def test_unavailable_platform_returns_table_only(self, member_client, workspace, accounts):
        _, li = accounts
        body = member_client.get(f"/api/web/workspaces/{workspace.id}/analytics/accounts/{li.id}").json()
        assert body["account"]["analytics_available"] is False
        assert body["table"]["rows"] == [] and body["table"]["metric_labels"] == []
        assert "hero_cards" not in body

    def test_fresh_account_has_no_metrics_yet(self, member_client, workspace, accounts):
        yt, _ = accounts
        r = member_client.get(f"/api/web/workspaces/{workspace.id}/analytics/accounts/{yt.id}?range=7")
        assert r.status_code == 200
        body = r.json()
        assert body["days"] == 7
        if body["account"]["analytics_available"]:
            assert body["is_fresh"] is True and "hero_cards" not in body

    def test_unknown_account_404(self, member_client, workspace):
        r = member_client.get(
            f"/api/web/workspaces/{workspace.id}/analytics/accounts/00000000-0000-0000-0000-000000000000"
        )
        assert r.status_code == 404


def _account(workspace, platform, name):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform=platform,
        account_platform_id=f"{platform}-1",
        account_name=name,
        oauth_access_token="token",
        connection_status=SocialAccount.ConnectionStatus.CONNECTED,
    )


def _disable_analytics(platform):
    AnalyticsPlatformConfig.objects.update_or_create(platform=platform, defaults={"is_enabled": False})


@pytest.mark.django_db
class TestAccountList:
    """Regression cover for accounts disappearing from the account switcher.

    A platform switched off in ``AnalyticsPlatformConfig`` used to be filtered
    out of the list feeding the switcher, so a connected Instagram (Direct)
    account simply wasn't there and nothing anywhere said why.
    """

    def _index(self, client, workspace):
        return client.get(f"/api/web/workspaces/{workspace.id}/analytics").json()

    def _account(self, client, workspace, account):
        r = client.get(f"/api/web/workspaces/{workspace.id}/analytics/accounts/{account.id}")
        assert r.status_code == 200
        return r.json()

    def test_instagram_direct_account_is_listed_and_available(self, member_client, workspace):
        account = _account(workspace, "instagram_login", "Direct IG")
        body = self._index(member_client, workspace)
        assert [a["id"] for a in body["accounts"]] == [str(account.id)]
        assert body["accounts"][0]["analytics_available"] is True

    def test_disabled_platform_account_stays_listed_with_a_reason(self, member_client, workspace):
        account = _account(workspace, "instagram_login", "Direct IG")
        _disable_analytics("instagram_login")
        body = self._account(member_client, workspace, account)
        assert [a["id"] for a in body["accounts"]] == [str(account.id)]
        assert body["account"]["analytics_available"] is False
        assert body["account"]["disabled_by_admin"] is True
        assert body["account"]["unavailable_reason"]

    def test_index_lands_on_the_only_account_even_when_disabled(self, member_client, workspace):
        """Better to land on the explanation than on "connect an account"."""
        account = _account(workspace, "instagram_login", "Direct IG")
        _disable_analytics("instagram_login")
        body = self._index(member_client, workspace)
        assert body["preferred_account_id"] == str(account.id)
        assert body["accounts"][0]["analytics_available"] is False

    def test_index_prefers_an_account_with_analytics_available(self, member_client, workspace):
        disabled = _account(workspace, "facebook", "AAA Disabled")
        available = _account(workspace, "instagram_login", "ZZZ Available")
        _disable_analytics("facebook")
        # "facebook" sorts first and would win on ordering alone; availability wins.
        assert disabled.platform < available.platform
        assert self._index(member_client, workspace)["preferred_account_id"] == str(available.id)

    def test_inherently_unavailable_platform_is_not_an_admin_toggle(self, member_client, workspace):
        """Bluesky has no analytics API — reconnecting or enabling would achieve nothing."""
        account = _account(workspace, "bluesky", "Bluesky")
        entry = self._account(member_client, workspace, account)["account"]
        assert entry["analytics_available"] is False
        assert entry["disabled_by_admin"] is False
        assert entry["needs_reconnect"] is False

    def test_disconnected_account_is_not_listed(self, member_client, workspace):
        """The connection-status filter is the one that still drops accounts."""
        listed = _account(workspace, "instagram_login", "Direct IG")
        dropped = _account(workspace, "threads", "Threads")
        dropped.connection_status = SocialAccount.ConnectionStatus.ERROR
        dropped.save(update_fields=["connection_status"])
        assert [a["id"] for a in self._index(member_client, workspace)["accounts"]] == [str(listed.id)]

    def test_devto_account_gets_the_unavailable_state(self, member_client, workspace):
        """DEV.to has no metrics methods and no entry in the PLATFORM_* maps.

        A missing config row counts as enabled, so the platform-keyed lookups
        all have to tolerate it rather than KeyError.
        """
        account = _account(workspace, "devto", "Dev Blog")
        body = self._account(member_client, workspace, account)
        assert body["account"]["analytics_available"] is False
        assert body["account"]["disabled_by_admin"] is False
        assert body["table"]["metric_labels"] == []
