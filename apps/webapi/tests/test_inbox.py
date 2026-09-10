"""Inbox through the web API: feed filters, thread, reply, triage, bulk, saved replies, SLA."""

from __future__ import annotations

import json
import secrets
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.inbox.models import InboxMessage, InboxSLAConfig, SavedReply
from apps.social_accounts.models import SocialAccount


@pytest.fixture
def account(workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="facebook",
        account_platform_id="pg",
        account_name="Page",
        connection_status="connected",
    )


def _msg(workspace, account, **kw):
    fields = dict(
        workspace=workspace,
        social_account=account,
        platform_message_id=f"m-{secrets.token_hex(3)}",
        message_type="comment",
        sender_name="Ada",
        sender_handle="ada",
        body="Do you ship to Canada?",
        received_at=timezone.now(),
    )
    fields.update(kw)
    return InboxMessage.objects.create(**fields)


def _post(client, path, data, method="post"):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    return getattr(client, method)(path, data=json.dumps(data), content_type="application/json", HTTP_X_CSRFTOKEN=token)


@pytest.mark.django_db
class TestFeedAndThread:
    def test_feed_filters_and_counts(self, member_client, workspace, account, org_owner):
        _msg(workspace, account, body="unread one")
        mine = _msg(workspace, account, body="mine", status="open", assigned_to=org_owner)
        _msg(workspace, account, body="spam", status="archived", sentiment="negative")
        base = f"/api/web/workspaces/{workspace.id}/inbox"

        body = member_client.get(base).json()
        assert len(body["messages"]) == 3 and body["unread_count"] == 1
        assert body["accounts"][0]["name"] == "Page" and body["can_reply"] is True

        assert [m["id"] for m in member_client.get(f"{base}?view=mine").json()["messages"]] == [str(mine.id)]
        assert len(member_client.get(f"{base}?status=archived").json()["messages"]) == 1
        assert len(member_client.get(f"{base}?q=canada").json()["messages"]) == 0
        assert len(member_client.get(f"{base}?q=spam").json()["messages"]) == 1
        assert len(member_client.get(f"{base}?sentiment=negative").json()["messages"]) == 1

    def test_detail_opens_unread_and_lists_thread(self, member_client, workspace, account, org_owner):
        from apps.inbox.models import InboxReply, InternalNote

        m = _msg(workspace, account)
        InboxReply.objects.create(inbox_message=m, author=org_owner, body="Yes!", platform_reply_id="r1")
        InternalNote.objects.create(inbox_message=m, author=org_owner, body="VIP")
        SavedReply.objects.create(workspace=workspace, title="Ship", body="We ship worldwide", created_by=org_owner)
        r = member_client.get(f"/api/web/workspaces/{workspace.id}/inbox/{m.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "open"
        assert [t["kind"] for t in body["thread"]] == ["reply", "note"]
        assert body["saved_replies"][0]["title"] == "Ship"


@pytest.mark.django_db
class TestMutations:
    def test_reply_note_triage_assign(self, member_client, workspace, account, org_owner):
        m = _msg(workspace, account)
        base = f"/api/web/workspaces/{workspace.id}/inbox/{m.id}"
        with patch("apps.inbox.services.send_platform_reply", return_value="c-1"):
            r = _post(member_client, f"{base}/reply", {"body": "Yes we do"})
        assert r.status_code == 200 and r.json()["delivered"] is True

        with patch("apps.inbox.services.send_platform_reply", side_effect=RuntimeError("no")):
            r = _post(member_client, f"{base}/reply", {"body": "again"})
        assert r.status_code == 502 and "rejected" in r.json()["detail"]

        assert _post(member_client, f"{base}/note", {"body": "internal"}).status_code == 200
        r = _post(member_client, f"{base}/triage", {"status": "resolved", "sentiment": "positive"})
        assert r.json()["status"] == "resolved" and r.json()["sentiment_source"] == "manual"
        r = _post(member_client, f"{base}/assign", {"user_id": str(org_owner.pk)})
        assert r.json()["assigned_to"]["id"] == str(org_owner.pk)
        r = _post(member_client, f"{base}/assign", {"user_id": None})
        assert r.json()["assigned_to"] is None

    def test_bulk(self, member_client, workspace, account):
        a, b = _msg(workspace, account), _msg(workspace, account)
        r = _post(
            member_client,
            f"/api/web/workspaces/{workspace.id}/inbox/bulk",
            {"message_ids": [str(a.id), str(b.id)], "action": "archive"},
        )
        assert r.json()["touched"] == 2
        assert set(InboxMessage.objects.filter(id__in=[a.id, b.id]).values_list("status", flat=True)) == {"archived"}

    def test_saved_replies_and_sla(self, member_client, workspace):
        base = f"/api/web/workspaces/{workspace.id}/inbox"
        r = _post(member_client, f"{base}/saved-replies", {"title": "Hi", "body": "Hello there"})
        rid = r.json()["id"]
        r = _post(member_client, f"{base}/saved-replies/{rid}", {"title": "Hi!", "body": "Hello"}, method="put")
        assert r.json()["title"] == "Hi!"
        assert member_client.get(f"{base}/saved-replies").json()["saved_replies"][0]["body"] == "Hello"
        token = secrets.token_hex(16)
        member_client.cookies["csrftoken"] = token
        assert member_client.delete(f"{base}/saved-replies/{rid}", HTTP_X_CSRFTOKEN=token).status_code == 200

        r = _post(
            member_client,
            f"{base}/sla",
            {"is_active": True, "target_response_minutes": 60, "auto_resolve_on_reply": True},
            method="put",
        )
        assert r.json()["target_response_minutes"] == 60
        assert InboxSLAConfig.objects.get(workspace=workspace).is_active is True
