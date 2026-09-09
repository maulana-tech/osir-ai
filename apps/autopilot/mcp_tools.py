"""MCP tools the agent uses to report its own runs.

``record_run`` is for scheduled loops (one call at the end). Command runs
created by the console are ``pending`` rows: a runner claims one with
``claim_pending_run`` and closes it with ``finish_run``.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.autopilot.models import AgentRun
from apps.mcp.handlers import _parse_uuid, _wrap_text
from apps.mcp.protocol import INVALID_PARAMS, JsonRpcError
from apps.mcp.tools import Tool, register_tool

_TASKS = list(AgentRun.Task.values)


def serialize_run(run: AgentRun) -> dict:
    return {
        "id": str(run.id),
        "task": run.task,
        "status": run.status,
        "dry_run": run.dry_run,
        "instruction": run.instruction,
        "triggered_by": run.triggered_by.display_name if run.triggered_by is not None else None,
        "report": run.report,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _record_run(args: dict, context: dict[str, Any]) -> dict:
    task = args.get("task")
    if task not in _TASKS:
        raise JsonRpcError(INVALID_PARAMS, f"task must be one of {_TASKS}")
    now = timezone.now()
    run = AgentRun.objects.create(
        workspace_id=context["api_key"].workspace_id,
        task=task,
        status=AgentRun.Status.FAILED if args.get("error") else AgentRun.Status.SUCCEEDED,
        dry_run=bool(args.get("dry_run", False)),
        instruction=args.get("instruction") or "",
        report=args.get("report") or {},
        error=args.get("error") or "",
        started_at=now,
        finished_at=now,
    )
    return _wrap_text(serialize_run(run))


register_tool(
    Tool(
        name="record_run",
        description=(
            "Record a completed scheduled run (inbox / calendar / digest) with its structured report so the "
            "team can see what the agent did. Called once at the end of a run by the runner, not by the model."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "enum": _TASKS},
                "dry_run": {"type": "boolean", "default": False},
                "instruction": {"type": "string"},
                "report": {"type": "object"},
                "error": {"type": "string"},
            },
            "required": ["task"],
            "additionalProperties": False,
        },
        handler=_record_run,
    )
)


def _claim_pending_run(args: dict, context: dict[str, Any]) -> dict:
    with transaction.atomic():
        run = (
            AgentRun.objects.select_for_update(skip_locked=True)
            .filter(workspace_id=context["api_key"].workspace_id, status=AgentRun.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        if run is None:
            return _wrap_text({"run": None})
        run.status = AgentRun.Status.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=["status", "started_at"])
    return _wrap_text({"run": serialize_run(run)})


register_tool(
    Tool(
        name="claim_pending_run",
        description=(
            "Runner-only: atomically claim the oldest pending command run in this workspace (marks it running) "
            "and return it, or {run: null} when nothing is waiting."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_claim_pending_run,
    )
)


def _finish_run(args: dict, context: dict[str, Any]) -> dict:
    if "run_id" not in args:
        raise JsonRpcError(INVALID_PARAMS, "run_id is required")
    run_id = _parse_uuid(args["run_id"], "run_id")
    try:
        run = AgentRun.objects.get(id=run_id, workspace_id=context["api_key"].workspace_id)
    except AgentRun.DoesNotExist as exc:
        raise JsonRpcError(INVALID_PARAMS, "Run not found") from exc
    if run.status in (AgentRun.Status.SUCCEEDED, AgentRun.Status.FAILED):
        raise JsonRpcError(INVALID_PARAMS, "Run already finished")
    error = args.get("error") or ""
    run.report = args.get("report") or {}
    run.error = error
    run.status = AgentRun.Status.FAILED if error else AgentRun.Status.SUCCEEDED
    run.finished_at = timezone.now()
    if run.started_at is None:
        run.started_at = run.finished_at
    run.save(update_fields=["report", "error", "status", "finished_at", "started_at"])
    return _wrap_text(serialize_run(run))


register_tool(
    Tool(
        name="finish_run",
        description="Runner-only: close a claimed command run with its structured report, or an error message.",
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "format": "uuid"},
                "report": {"type": "object"},
                "error": {"type": "string"},
            },
            "required": ["run_id"],
            "additionalProperties": False,
        },
        handler=_finish_run,
    )
)
