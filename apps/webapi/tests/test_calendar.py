"""Calendar window and drag-and-drop reschedule through the web API."""

from __future__ import annotations

import datetime as dt
import json
import secrets

import pytest
from django.utils import timezone

from apps.calendar.models import PostingSlot
from apps.composer.models import PlatformPost, Post
from apps.composer.services import create_post
from apps.social_accounts.models import SocialAccount


@pytest.fixture
def account(workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id="li",
        account_name="Me",
        connection_status="connected",
    )


def _csrf(client):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    return token


@pytest.mark.django_db
class TestCalendarWindow:
    def test_chips_slots_and_drafts_in_window(self, member_client, workspace, account):
        when = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + dt.timedelta(days=3)
        create_post(
            workspace=workspace, social_account=account, caption="Planned", scheduled_at=when, status="scheduled"
        )
        create_post(workspace=workspace, social_account=account, caption="Loose draft")
        # A slot on the scheduled day at another time stays open; one at the same minute is taken.
        PostingSlot.objects.create(social_account=account, day_of_week=when.weekday(), time=dt.time(10, 0))
        PostingSlot.objects.create(social_account=account, day_of_week=when.weekday(), time=dt.time(15, 30))

        start = when.date() - dt.timedelta(days=1)
        end = when.date() + dt.timedelta(days=1)
        r = member_client.get(f"/api/web/workspaces/{workspace.id}/calendar?start={start}&end={end}&tz=UTC")
        assert r.status_code == 200
        body = r.json()
        assert [c["caption"] for c in body["chips"]] == ["Planned"]
        assert body["chips"][0]["is_reschedulable"] is True
        assert [s["compose_time"] for s in body["open_slots"]] == ["15:30"]
        assert [d["caption"] for d in body["unscheduled_drafts"]] == ["Loose draft"]
        assert body["filters"]["channels"][0]["name"] == "Me"

    def test_window_limits(self, member_client, workspace):
        r = member_client.get(f"/api/web/workspaces/{workspace.id}/calendar?start=2026-01-01&end=2026-06-01")
        assert r.status_code == 400

    def test_status_and_channel_filters_anchor_to_the_same_row(self, member_client, workspace, account):
        """A post pending on one channel and drafted on another must not surface
        (or become bulk-actionable) under the other channel + pending filter."""
        other = SocialAccount.objects.create(
            workspace=workspace,
            platform="instagram_business",
            account_platform_id="ig",
            account_name="IG",
            connection_status="connected",
        )
        when = timezone.now() + dt.timedelta(days=2)
        post = Post.objects.create(workspace=workspace, caption="MIXEDROW", scheduled_at=when)
        PlatformPost.objects.create(post=post, social_account=other, status="pending_review")
        PlatformPost.objects.create(post=post, social_account=account, status="draft")
        base = f"/api/web/workspaces/{workspace.id}/calendar?start={when.date()}&end={when.date()}&tz=UTC"
        base += "&status=pending_review"
        assert member_client.get(f"{base}&channel={account.id}").json()["chips"] == []
        assert [c["caption"] for c in member_client.get(f"{base}&channel={other.id}").json()["chips"]] == ["MIXEDROW"]
        r = member_client.get(f"/api/web/workspaces/{workspace.id}/calendar?start=2026-02-01&end=2026-01-01")
        assert r.status_code == 400


@pytest.mark.django_db
class TestReschedule:
    def test_moves_a_scheduled_chip_in_the_display_timezone(self, member_client, workspace, account):
        when = timezone.now() + dt.timedelta(days=2)
        post = create_post(
            workspace=workspace, social_account=account, caption="x", scheduled_at=when, status="scheduled"
        )
        pp = post.platform_posts.get()
        token = _csrf(member_client)
        r = member_client.post(
            f"/api/web/workspaces/{workspace.id}/calendar/reschedule",
            data=json.dumps({"platform_post_id": str(pp.id), "new_local": "2030-05-01T09:30", "tz": "Asia/Jakarta"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert r.status_code == 200, r.content
        pp.refresh_from_db()
        assert pp.scheduled_at == dt.datetime(2030, 5, 1, 2, 30, tzinfo=dt.UTC)  # 09:30 WIB
        post.refresh_from_db()
        assert post.scheduled_at == pp.scheduled_at

    def test_dropping_a_draft_schedules_it(self, member_client, workspace, account):
        post = create_post(workspace=workspace, social_account=account, caption="draft")
        pp = post.platform_posts.get()
        token = _csrf(member_client)
        r = member_client.post(
            f"/api/web/workspaces/{workspace.id}/calendar/reschedule",
            data=json.dumps({"platform_post_id": str(pp.id), "new_local": "2030-05-01T09:30"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert r.status_code == 200
        pp.refresh_from_db()
        assert pp.status == PlatformPost.Status.SCHEDULED

    def test_published_chip_cannot_move(self, member_client, workspace, account):
        post = create_post(workspace=workspace, social_account=account, caption="done")
        pp = post.platform_posts.get()
        PlatformPost.objects.filter(id=pp.id).update(status="published")
        token = _csrf(member_client)
        r = member_client.post(
            f"/api/web/workspaces/{workspace.id}/calendar/reschedule",
            data=json.dumps({"platform_post_id": str(pp.id), "new_local": "2030-05-01T09:30"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert r.status_code == 400
