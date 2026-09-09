"""Autopilot MCP tools — inbox, ideas, schedule, approvals, notify_team.

Reuses the transport fixtures (owner key scoped to ``social_account``) and
exercises each tool through the real JSON-RPC surface so allowlist and
permission gates are tested as the agent would hit them.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.api_keys import services as key_services
from apps.mcp.protocol import INVALID_PARAMS
from apps.mcp.tests.test_transport import _post, _rpc, _SecureClient


def _call(client, name, **arguments):
    status, body = _post(client, _rpc("tools/call", {"name": name, "arguments": arguments}))
    assert status == 200, body
    if "error" in body:
        return body["error"]
    return json.loads(body["result"]["content"][0]["text"])


def _message(workspace, account, **overrides):
    from apps.inbox.models import InboxMessage

    fields = {
        "workspace": workspace,
        "social_account": account,
        "platform_message_id": f"pm-{timezone.now().timestamp()}",
        "message_type": InboxMessage.MessageType.COMMENT,
        "sender_name": "Ada",
        "sender_handle": "ada",
        "body": "Do you ship to Canada?",
        "received_at": timezone.now(),
    }
    fields.update(overrides)
    return InboxMessage.objects.create(**fields)


@pytest.fixture
def limited_client(db, user, owner_memberships, workspace, social_account):
    """A key that can read the inbox but not reply/annotate."""
    key = key_services.issue_api_key(
        workspace=workspace,
        social_accounts=[social_account],
        issued_by=user,
        name="reader",
        permissions=["use_inbox", "view_analytics"],
    )
    return _SecureClient(HTTP_AUTHORIZATION=f"Bearer {key.plaintext_token}")


@pytest.mark.django_db
class TestCatalog:
    def test_autopilot_tools_are_listed(self, client_with_token):
        _, body = _post(client_with_token, _rpc("tools/list"))
        names = {t["name"] for t in body["result"]["tools"]}
        assert {
            "list_inbox_messages",
            "get_inbox_message",
            "list_saved_replies",
            "reply_to_inbox_message",
            "triage_inbox_message",
            "list_ideas",
            "get_schedule",
            "submit_for_approval",
            "notify_team",
        } <= names


@pytest.mark.django_db
class TestInboxTools:
    def test_list_respects_allowlist_and_unanswered_filter(
        self, client_with_token, workspace, social_account, second_account, user
    ):
        from apps.inbox.models import InboxReply

        visible = _message(workspace, social_account)
        answered = _message(workspace, social_account, body="Thanks!")
        InboxReply.objects.create(inbox_message=answered, author=user, body="You're welcome")
        _message(workspace, second_account, body="hidden")

        result = _call(client_with_token, "list_inbox_messages")
        assert {m["id"] for m in result["messages"]} == {str(visible.id), str(answered.id)}

        result = _call(client_with_token, "list_inbox_messages", unanswered_only=True)
        assert [m["id"] for m in result["messages"]] == [str(visible.id)]
        assert result["messages"][0]["reply_count"] == 0

    def test_get_message_includes_thread(self, client_with_token, workspace, social_account, user):
        from apps.inbox.models import InboxReply, InternalNote

        parent = _message(workspace, social_account, body="Original post comment")
        child = _message(workspace, social_account, body="Follow-up", parent_message=parent)
        InboxReply.objects.create(inbox_message=child, author=user, body="Sure!", platform_reply_id="r1")
        InternalNote.objects.create(inbox_message=child, author=user, body="VIP customer")

        result = _call(client_with_token, "get_inbox_message", message_id=str(child.id))
        assert result["parent"]["body"] == "Original post comment"
        assert result["replies"][0]["delivered"] is True
        assert result["internal_notes"][0]["body"] == "VIP customer"

    def test_hidden_message_is_not_found(self, client_with_token, workspace, second_account):
        hidden = _message(workspace, second_account)
        err = _call(client_with_token, "get_inbox_message", message_id=str(hidden.id))
        assert err["code"] == INVALID_PARAMS

    def test_reply_sends_via_platform_and_records(self, client_with_token, workspace, social_account, user):
        from apps.inbox.models import InboxMessage, InboxReply

        m = _message(workspace, social_account)
        with patch("apps.inbox.services.send_platform_reply", return_value="c-99") as send:
            result = _call(client_with_token, "reply_to_inbox_message", message_id=str(m.id), body="Yes, we do!")
        send.assert_called_once()
        assert result["delivered"] is True
        reply = InboxReply.objects.get(inbox_message=m)
        assert reply.author == user
        assert reply.platform_reply_id == "c-99"
        m.refresh_from_db()
        assert m.status == InboxMessage.Status.OPEN

    def test_reply_failure_is_reported_not_recorded(self, client_with_token, workspace, social_account):
        from apps.inbox.models import InboxReply

        m = _message(workspace, social_account)
        with patch("apps.inbox.services.send_platform_reply", side_effect=RuntimeError("nope")):
            err = _call(client_with_token, "reply_to_inbox_message", message_id=str(m.id), body="Hi")
        assert "rejected" in err["message"]
        assert not InboxReply.objects.filter(inbox_message=m).exists()

    def test_reply_requires_permission(self, limited_client, workspace, social_account):
        m = _message(workspace, social_account)
        err = _call(limited_client, "reply_to_inbox_message", message_id=str(m.id), body="Hi")
        assert err["code"] == INVALID_PARAMS

    def test_triage_sets_status_and_note(self, client_with_token, workspace, social_account, user):
        from apps.inbox.models import InboxMessage, InternalNote

        m = _message(workspace, social_account)
        result = _call(
            client_with_token,
            "triage_inbox_message",
            message_id=str(m.id),
            status="resolved",
            sentiment="negative",
            internal_note="Escalated: refund request",
        )
        assert result["status"] == "resolved"
        m.refresh_from_db()
        assert m.sentiment == InboxMessage.Sentiment.NEGATIVE
        assert m.sentiment_source == InboxMessage.SentimentSource.MANUAL
        note = InternalNote.objects.get(inbox_message=m)
        assert note.author == user

    def test_triage_note_requires_reply_permission(self, limited_client, workspace, social_account):
        m = _message(workspace, social_account)
        assert _call(limited_client, "triage_inbox_message", message_id=str(m.id), status="open")["status"] == "open"
        err = _call(limited_client, "triage_inbox_message", message_id=str(m.id), internal_note="x")
        assert err["code"] == INVALID_PARAMS

    def test_saved_replies(self, client_with_token, workspace, user):
        from apps.inbox.models import SavedReply

        SavedReply.objects.create(workspace=workspace, title="Shipping", body="We ship worldwide.", created_by=user)
        result = _call(client_with_token, "list_saved_replies")
        assert result["saved_replies"][0]["title"] == "Shipping"


@pytest.mark.django_db
class TestIdeasAndDrafts:
    def test_list_ideas_then_draft_from_idea(self, client_with_token, workspace, social_account, user):
        from apps.composer.models import Idea

        idea = Idea.objects.create(workspace=workspace, author=user, title="Launch teaser", tags=["launch"])
        result = _call(client_with_token, "list_ideas")
        assert [i["id"] for i in result["ideas"]] == [str(idea.id)]

        post = _call(
            client_with_token,
            "create_draft",
            social_account_id=str(social_account.id),
            caption="Something big is coming.",
            idea_id=str(idea.id),
        )
        idea.refresh_from_db()
        assert str(idea.post_id) == post["id"]
        assert idea.status == Idea.Status.IN_PROGRESS
        assert _call(client_with_token, "list_ideas")["ideas"] == []

        err = _call(
            client_with_token,
            "create_draft",
            social_account_id=str(social_account.id),
            caption="Again",
            idea_id=str(idea.id),
        )
        assert err["code"] == INVALID_PARAMS


@pytest.mark.django_db
class TestScheduleAndApproval:
    def test_get_schedule_returns_slots_and_posts(self, client_with_token, workspace, social_account, second_account):
        from apps.calendar.models import PostingSlot
        from apps.composer.services import create_post

        PostingSlot.objects.create(social_account=social_account, day_of_week=0, time=dt.time(9, 0))
        PostingSlot.objects.create(social_account=second_account, day_of_week=1, time=dt.time(9, 0))
        when = timezone.now() + dt.timedelta(days=2)
        create_post(
            workspace=workspace, social_account=social_account, caption="Planned", scheduled_at=when, status="scheduled"
        )

        start = timezone.now().isoformat()
        end = (timezone.now() + dt.timedelta(days=7)).isoformat()
        result = _call(client_with_token, "get_schedule", start=start, end=end)
        assert len(result["posting_slots"]) == 1
        assert result["posting_slots"][0]["time"] == "09:00"
        assert len(result["posts"]) == 1
        assert result["posts"][0]["status"] == "scheduled"

        err = _call(client_with_token, "get_schedule", start=start, end=start)
        assert err["code"] == INVALID_PARAMS

    def test_submit_for_approval(self, client_with_token, workspace, social_account, user):
        from apps.approvals.models import ApprovalAction
        from apps.composer.services import create_post

        post = create_post(workspace=workspace, social_account=social_account, caption="Review me")
        result = _call(client_with_token, "submit_for_approval", post_id=str(post.id))
        assert result["platform_posts"][0]["status"] == "pending_review"
        assert ApprovalAction.objects.filter(post=post, user=user, action="submitted").exists()

        err = _call(client_with_token, "submit_for_approval", post_id=str(post.id))
        assert err["code"] == INVALID_PARAMS


@pytest.mark.django_db
class TestNotifyTeam:
    def test_decision_notifies_issuer(self, client_with_token, workspace, social_account, user):
        from apps.notifications.models import Notification

        m = _message(workspace, social_account)
        result = _call(
            client_with_token,
            "notify_team",
            title="Refund request needs you",
            body="Ada asked for a refund on order #12",
            message_id=str(m.id),
        )
        assert result["notified"] == 1
        n = Notification.objects.get(user=user)
        assert n.event_type == "agent_decision_needed"
        assert n.data["message_id"] == str(m.id)

    def test_digest_kind(self, client_with_token, user):
        from apps.notifications.models import Notification

        _call(client_with_token, "notify_team", title="Weekly digest", kind="digest")
        assert Notification.objects.get(user=user).event_type == "agent_digest"


@pytest.mark.django_db
class TestWorkspacePolicy:
    def test_policy_reflects_workspace_dial_and_key_permissions(self, client_with_token, limited_client, workspace):
        from apps.workspaces.models import Workspace

        policy = _call(client_with_token, "get_workspace_policy")
        assert policy["agent_autonomy"] == "draft_only"
        assert policy["direct_scheduling_allowed"] is True
        assert policy["can_publish"] is True

        workspace.agent_autonomy = Workspace.AgentAutonomy.AUTOPILOT
        workspace.approval_workflow_mode = Workspace.ApprovalWorkflowMode.REQUIRED_INTERNAL
        workspace.save()
        policy = _call(limited_client, "get_workspace_policy")
        assert policy["agent_autonomy"] == "autopilot"
        assert policy["direct_scheduling_allowed"] is False
        assert policy["can_publish"] is False
        assert "publish_directly" not in policy["permissions"]
