"""REST surface for the Osir Console (``web/``): ``/api/v1/agent/*``.

Same bearer auth, rate limits and audit log as the rest of the Agent API.
The console holds one workspace-scoped key server-side; every write is
attributed to that key's issuer, like the agent's own actions.
"""

from __future__ import annotations

import uuid

from django.db.models import Exists, OuterRef
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.api.limits import enforce_http_rate_limits
from apps.api.middleware import log_audit_entry
from apps.api.routers.posts import _get_workspace_post, _post_to_response, _require_perm
from apps.api.schemas import PostResponse
from apps.approvals.services import approve_post, reject_post
from apps.composer.models import PlatformPost, Post
from apps.composer.services import _APPROVAL_MODES_BLOCKING_DIRECT_SCHEDULE
from apps.notifications.models import EventType, Notification
from apps.workspaces.models import Workspace

from .mcp_tools import serialize_run
from .models import AgentRun
from .tasks import agentcore_configured, invoke_agentcore

router = Router(tags=["agent"])

_AGENT_EVENTS = (EventType.AGENT_DECISION_NEEDED, EventType.AGENT_DIGEST)


def _issuer(request: HttpRequest):
    user = request.api_key.issued_by  # type: ignore[attr-defined]
    if user is None:
        raise HttpError(400, "This API key has no issuing user; re-issue it to use the console")
    return user


# ---------------------------------------------------------------------------
# Runs and commands
# ---------------------------------------------------------------------------


class CommandRequest(Schema):
    instruction: str
    dry_run: bool = False


@router.get("/runs", summary="Recent agent runs, newest first")
def list_runs(request, limit: int = 30, status: str | None = None):
    enforce_http_rate_limits(request, is_write=False)
    qs = AgentRun.objects.for_workspace(request.workspace.id).select_related("triggered_by")
    if status:
        qs = qs.filter(status=status)
    limit = max(1, min(limit, 100))
    runs = [serialize_run(r) for r in qs[:limit]]
    log_audit_entry(request, action="agent.runs.list", target_id=None, status_code=200)
    return {"runs": runs}


@router.get("/runs/{run_id}", summary="One agent run with its full report")
def get_run(request, run_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=False)
    try:
        run = AgentRun.objects.for_workspace(request.workspace.id).select_related("triggered_by").get(id=run_id)
    except AgentRun.DoesNotExist as exc:
        raise HttpError(404, "Run not found") from exc
    return serialize_run(run)


@router.post("/command", summary="Ask the agent to do something now")
def command(request, payload: CommandRequest):
    enforce_http_rate_limits(request, is_write=True)
    _require_perm(request, "create_posts")
    instruction = payload.instruction.strip()
    if not instruction:
        raise HttpError(400, "instruction is required")
    run = AgentRun.objects.create(
        workspace=request.workspace,
        task=AgentRun.Task.COMMAND,
        dry_run=payload.dry_run,
        instruction=instruction[:4000],
        triggered_by=_issuer(request),
    )
    if agentcore_configured():
        invoke_agentcore(str(run.id))
    log_audit_entry(request, action="agent.command", target_id=run.id, status_code=201)
    return serialize_run(run)


# ---------------------------------------------------------------------------
# Decisions (agent notifications addressed to the console's user)
# ---------------------------------------------------------------------------


def _serialize_notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "event_type": n.event_type,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat(),
    }


@router.get("/decisions", summary="Decisions and digests the agent surfaced")
def list_decisions(request, unread_only: bool = False, limit: int = 50):
    enforce_http_rate_limits(request, is_write=False)
    qs = Notification.objects.filter(
        user=_issuer(request),
        event_type__in=_AGENT_EVENTS,
        data__workspace_id=str(request.workspace.id),
    )
    if unread_only:
        qs = qs.filter(is_read=False)
    limit = max(1, min(limit, 200))
    return {"decisions": [_serialize_notification(n) for n in qs[:limit]]}


@router.post("/decisions/{notification_id}/read", summary="Mark a decision as handled")
def mark_decision_read(request, notification_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    try:
        n = Notification.objects.get(id=notification_id, user=_issuer(request), event_type__in=_AGENT_EVENTS)
    except Notification.DoesNotExist as exc:
        raise HttpError(404, "Decision not found") from exc
    if not n.is_read:
        n.is_read = True
        n.read_at = timezone.now()
        n.save(update_fields=["is_read", "read_at"])
    return _serialize_notification(n)


# ---------------------------------------------------------------------------
# Policy (the autonomy dial)
# ---------------------------------------------------------------------------


class PolicyUpdate(Schema):
    agent_autonomy: str


def _policy(request: HttpRequest) -> dict:
    ws = request.workspace  # type: ignore[attr-defined]
    perms = request.workspace_membership.effective_permissions  # type: ignore[attr-defined]
    return {
        "workspace_id": str(ws.id),
        "workspace_name": ws.name,
        "timezone": ws.timezone or "UTC",
        "agent_autonomy": ws.agent_autonomy,
        "autonomy_levels": list(Workspace.AgentAutonomy.values),
        "approval_workflow_mode": ws.approval_workflow_mode,
        "direct_scheduling_allowed": ws.approval_workflow_mode not in _APPROVAL_MODES_BLOCKING_DIRECT_SCHEDULE,
        "can_publish": bool(perms.get("publish_directly")),
        "can_change_policy": bool(perms.get("manage_workspace_settings")),
        "agentcore_configured": agentcore_configured(),
    }


@router.get("/policy", summary="The workspace's autopilot policy")
def get_policy(request):
    enforce_http_rate_limits(request, is_write=False)
    return _policy(request)


@router.patch("/policy", summary="Change the autonomy dial")
def update_policy(request, payload: PolicyUpdate):
    enforce_http_rate_limits(request, is_write=True)
    _require_perm(request, "manage_workspace_settings")
    if payload.agent_autonomy not in Workspace.AgentAutonomy.values:
        raise HttpError(400, f"agent_autonomy must be one of {list(Workspace.AgentAutonomy.values)}")
    ws = request.workspace
    ws.agent_autonomy = payload.agent_autonomy
    ws.save(update_fields=["agent_autonomy", "updated_at"])
    log_audit_entry(request, action="agent.policy.update", target_id=ws.id, status_code=200)
    return _policy(request)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


class ReviewRequest(Schema):
    comment: str = ""


@router.get("/approvals", response=list[PostResponse], summary="Posts waiting for a human decision")
def list_approvals(request, limit: int = 50):
    enforce_http_rate_limits(request, is_write=False)
    allowed = [sa.id for sa in request.api_key.social_accounts.all()]
    if not allowed:
        return []
    children = PlatformPost.objects.filter(post_id=OuterRef("pk"))
    qs = (
        Post.objects.filter(workspace_id=request.workspace.id)
        .filter(Exists(children.filter(status__in=["pending_review", "pending_client"])))
        .exclude(Exists(children.exclude(social_account_id__in=allowed)))
        .prefetch_related("platform_posts__social_account")
        .order_by("-updated_at")
    )
    return [_post_to_response(request, p) for p in qs[: max(1, min(limit, 100))]]


@router.post("/approvals/{post_id}/approve", response=PostResponse, summary="Approve a post")
def approve(request, post_id: uuid.UUID, payload: ReviewRequest | None = None):
    enforce_http_rate_limits(request, is_write=True)
    _require_perm(request, "approve_posts")
    post = _get_workspace_post(request, post_id)
    result = approve_post(post, _issuer(request), request.workspace, comment=(payload.comment if payload else ""))
    if isinstance(result, list):
        raise HttpError(400, "Nothing to approve on this post")
    post.refresh_from_db()
    log_audit_entry(request, action="agent.approve", target_id=post.id, status_code=200)
    return _post_to_response(request, post)


@router.post("/approvals/{post_id}/reject", response=PostResponse, summary="Reject a post")
def reject(request, post_id: uuid.UUID, payload: ReviewRequest):
    enforce_http_rate_limits(request, is_write=True)
    _require_perm(request, "approve_posts")
    post = _get_workspace_post(request, post_id)
    result = reject_post(post, _issuer(request), request.workspace, payload.comment)
    if isinstance(result, list):
        raise HttpError(400, "Nothing to reject on this post")
    post.refresh_from_db()
    log_audit_entry(request, action="agent.reject", target_id=post.id, status_code=200)
    return _post_to_response(request, post)
