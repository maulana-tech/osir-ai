"""Osir Console surface: ``/api/v1/agent/*`` REST routes and the run-recording MCP tools.

Lives next to the MCP tests to reuse their owner-key fixtures (see conftest).
"""

from __future__ import annotations

import json

import pytest

from apps.autopilot.models import AgentRun
from apps.mcp.tests.test_transport import _post, _rpc

BASE = "/api/v1/agent"


def _tool(client, name, **arguments):
    status, body = _post(client, _rpc("tools/call", {"name": name, "arguments": arguments}))
    assert status == 200, body
    if "error" in body:
        return body["error"]
    return json.loads(body["result"]["content"][0]["text"])


def _json(client, method, path, data=None):
    r = getattr(client, method)(
        f"{BASE}{path}", data=json.dumps(data) if data is not None else None, content_type="application/json"
    )
    return r.status_code, (r.json() if r.content else None)


@pytest.mark.django_db
class TestRunRecording:
    def test_record_run_then_listed(self, client_with_token, workspace):
        out = _tool(client_with_token, "record_run", task="inbox", dry_run=True, report={"actions": []})
        assert out["status"] == "succeeded"
        status, body = _json(client_with_token, "get", "/runs")
        assert status == 200
        assert [r["id"] for r in body["runs"]] == [out["id"]]
        assert body["runs"][0]["report"] == {"actions": []}

    def test_command_creates_pending_run_that_a_runner_claims_and_finishes(self, client_with_token, user):
        status, run = _json(client_with_token, "post", "/command", {"instruction": "Plan next week"})
        assert status == 200 and run["status"] == "pending"
        assert run["triggered_by"] == user.display_name

        claimed = _tool(client_with_token, "claim_pending_run")["run"]
        assert claimed["id"] == run["id"] and claimed["status"] == "running"
        assert _tool(client_with_token, "claim_pending_run")["run"] is None

        done = _tool(client_with_token, "finish_run", run_id=run["id"], report={"notes": "drafted 3"})
        assert done["status"] == "succeeded"
        err = _tool(client_with_token, "finish_run", run_id=run["id"], report={})
        assert "already finished" in err["message"]

        status, body = _json(client_with_token, "get", f"/runs/{run['id']}")
        assert body["report"] == {"notes": "drafted 3"}

    def test_finish_with_error_marks_failed(self, client_with_token, workspace):
        run = AgentRun.objects.create(workspace=workspace, task="command", instruction="x")
        out = _tool(client_with_token, "finish_run", run_id=str(run.id), error="boom")
        assert out["status"] == "failed" and out["error"] == "boom"


@pytest.mark.django_db
class TestDecisionsAndPolicy:
    def test_decisions_list_and_read(self, client_with_token, user, workspace):
        _tool(client_with_token, "notify_team", title="Refund?", body="Ada wants a refund")
        status, body = _json(client_with_token, "get", "/decisions?unread_only=true")
        assert status == 200 and len(body["decisions"]) == 1
        nid = body["decisions"][0]["id"]
        status, n = _json(client_with_token, "post", f"/decisions/{nid}/read")
        assert n["is_read"] is True
        assert _json(client_with_token, "get", "/decisions?unread_only=true")[1]["decisions"] == []

    def test_policy_roundtrip(self, client_with_token, workspace):
        status, policy = _json(client_with_token, "get", "/policy")
        assert policy["agent_autonomy"] == "draft_only" and policy["can_change_policy"] is True
        status, policy = _json(client_with_token, "patch", "/policy", {"agent_autonomy": "autopilot"})
        assert status == 200 and policy["agent_autonomy"] == "autopilot"
        workspace.refresh_from_db()
        assert workspace.agent_autonomy == "autopilot"
        status, _ = _json(client_with_token, "patch", "/policy", {"agent_autonomy": "nope"})
        assert status == 400


@pytest.mark.django_db
class TestApprovals:
    def test_pending_posts_can_be_approved_or_rejected(self, client_with_token, workspace, social_account, user):
        from apps.approvals.services import submit_for_review
        from apps.composer.services import create_post

        a = create_post(workspace=workspace, social_account=social_account, caption="A")
        b = create_post(workspace=workspace, social_account=social_account, caption="B")
        submit_for_review(a, user, workspace)
        submit_for_review(b, user, workspace)

        status, pending = _json(client_with_token, "get", "/approvals")
        assert {p["id"] for p in pending} == {str(a.id), str(b.id)}

        status, out = _json(client_with_token, "post", f"/approvals/{a.id}/approve", {})
        assert status == 200 and out["platform_posts"][0]["status"] == "approved"
        status, out = _json(client_with_token, "post", f"/approvals/{b.id}/reject", {"comment": "Too salesy"})
        assert status == 200 and out["platform_posts"][0]["status"] == "rejected"
        assert _json(client_with_token, "get", "/approvals")[1] == []
