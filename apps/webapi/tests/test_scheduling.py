"""Calendar extras and the org calendar through the web API."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.calendar.models import CustomCalendarEvent, PostingSlot, Queue
from apps.composer.models import PlatformPost, Post
from apps.social_accounts.models import SocialAccount


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
class TestScheduling:
    def test_events_crud_and_window(self, member_client, workspace):
        base = f"/api/web/workspaces/{workspace.id}/calendar"
        r = _send(
            member_client,
            "post",
            f"{base}/events",
            {"title": "Launch", "start_date": "2030-01-10", "end_date": "2030-01-09", "color": "#123456"},
        )
        assert r.status_code == 200 and r.json()["end_date"] == "2030-01-10"
        eid = r.json()["id"]
        assert (
            _send(
                member_client, "post", f"{base}/events", {"title": "x", "start_date": "2030-01-10", "color": "red"}
            ).status_code
            == 400
        )
        window = member_client.get(f"{base}?start=2030-01-01&end=2030-01-31").json()
        assert [e["id"] for e in window["events"]] == [eid]
        assert (
            _send(
                member_client,
                "put",
                f"{base}/events/{eid}",
                {"title": "Launch 2", "start_date": "2030-02-01", "color": "#000000"},
            ).json()["title"]
            == "Launch 2"
        )
        assert _send(member_client, "delete", f"{base}/events/{eid}").status_code == 200
        assert not CustomCalendarEvent.objects.filter(id=eid).exists()

    def test_bulk_publish_and_delete(self, member_client, workspace, org_owner, account):
        post = Post.objects.create(workspace=workspace, author=org_owner, caption="c")
        pp = PlatformPost.objects.create(post=post, social_account=account, status="draft")
        base = f"/api/web/workspaces/{workspace.id}/calendar/bulk"
        r = _send(member_client, "post", base, {"action": "publish", "platform_post_ids": [str(pp.id)]})
        assert r.status_code == 200 and r.json()["count"] == 1
        pp.refresh_from_db()
        assert pp.status == "scheduled" and pp.scheduled_at is not None
        assert (
            _send(member_client, "post", base, {"action": "nope", "platform_post_ids": [str(pp.id)]}).status_code == 400
        )
        r = _send(member_client, "post", base, {"action": "delete", "platform_post_ids": [str(pp.id)]})
        assert r.json()["count"] == 1 and not Post.objects.filter(id=post.id).exists()

    def test_slots(self, member_client, workspace, account):
        base = f"/api/web/workspaces/{workspace.id}/calendar/slots"
        r = _send(
            member_client, "post", base, {"social_account_id": str(account.id), "day_of_week": 1, "time": "09:30"}
        )
        assert r.status_code == 200
        sid = r.json()["id"]
        _send(member_client, "post", base, {"social_account_id": str(account.id), "day_of_week": 1, "time": "10:00"})
        assert _send(member_client, "patch", f"{base}/{sid}", {"time": "10:00"}).status_code == 409
        assert _send(member_client, "patch", f"{base}/{sid}", {"time": "11:00"}).json()["time"] == "11:00"
        assert (
            _send(
                member_client, "post", f"{base}/toggle-day", {"social_account_id": str(account.id), "day_of_week": 1}
            ).json()["is_active"]
            is False
        )
        body = member_client.get(base).json()
        assert len(body["accounts"][0]["slots"]) == 2 and all(not s["is_active"] for s in body["accounts"][0]["slots"])
        assert _send(member_client, "delete", f"{base}/{sid}").status_code == 200
        assert PostingSlot.objects.filter(social_account=account).count() == 1

    def test_queues(self, member_client, workspace, org_owner, account):
        base = f"/api/web/workspaces/{workspace.id}/calendar/queues"
        r = _send(member_client, "post", base, {"name": "Main", "social_account_id": str(account.id)})
        assert r.status_code == 200
        qid = r.json()["id"]
        assert member_client.get(base).json()["queues"][0]["name"] == "Main"
        detail = member_client.get(f"{base}/{qid}").json()
        assert detail["queue"]["id"] == qid and detail["entries"] == []
        assert _send(member_client, "delete", f"{base}/{qid}").status_code == 200
        assert not Queue.objects.filter(id=qid).exists()

    def test_org_calendar(self, member_client, workspace, org_owner, account):
        when = timezone.now() + timedelta(days=1)
        post = Post.objects.create(workspace=workspace, author=org_owner, caption="c", scheduled_at=when)
        PlatformPost.objects.create(post=post, social_account=account, status="scheduled", scheduled_at=when)
        start = when.date().isoformat()
        body = member_client.get(f"/api/web/org/calendar?start={start}&end={start}").json()
        assert any(w["id"] == str(workspace.id) for w in body["workspaces"])
        assert len(body["chips"]) == 1 and body["chips"][0]["workspace_id"] == str(workspace.id)
        assert member_client.get("/api/web/org/calendar?start=2030-01-01&end=2030-12-31").status_code == 400

    def test_analytics_post_detail(self, member_client, workspace, org_owner, account):
        post = Post.objects.create(workspace=workspace, author=org_owner, caption="published!")
        pp = PlatformPost.objects.create(
            post=post, social_account=account, status="published", published_at=timezone.now()
        )
        body = member_client.get(f"/api/web/workspaces/{workspace.id}/analytics/posts/{pp.id}").json()
        assert body["caption"] == "published!" and body["account"]["platform"] == "facebook"
        assert isinstance(body["metric_tiles"], list)
