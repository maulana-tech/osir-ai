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
