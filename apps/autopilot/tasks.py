"""Hand a pending command run to Amazon Bedrock AgentCore Runtime.

Only used when ``AGENT_RUNTIME_ARN`` is configured. Without it, pending
runs wait for a local runner (``agent/run_local.py worker``), which claims
them through the ``claim_pending_run`` MCP tool.
"""

from __future__ import annotations

import json
import logging
import uuid

from background_task import background
from django.conf import settings
from django.utils import timezone

from .models import AgentRun

logger = logging.getLogger(__name__)


def agentcore_configured() -> bool:
    return bool(getattr(settings, "AGENT_RUNTIME_ARN", ""))


@background(schedule=0)
def invoke_agentcore(run_id: str) -> None:
    """Call ``InvokeAgentRuntime`` for one pending run and store its report."""
    import boto3

    try:
        run = AgentRun.objects.get(id=run_id)
    except AgentRun.DoesNotExist:
        return
    if run.status != AgentRun.Status.PENDING:
        return

    run.status = AgentRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    payload = {"task": run.task, "instruction": run.instruction, "dry_run": run.dry_run, "run_id": str(run.id)}
    try:
        client = boto3.client("bedrock-agentcore", region_name=settings.AGENT_RUNTIME_REGION)
        response = client.invoke_agent_runtime(
            agentRuntimeArn=settings.AGENT_RUNTIME_ARN,
            runtimeSessionId=f"osir-console-{uuid.uuid4()}",
            payload=json.dumps(payload).encode(),
            qualifier="DEFAULT",
        )
        body = json.loads(response["response"].read() or b"{}")
    except Exception as exc:
        logger.exception("AgentCore invocation failed for run %s", run.id)
        run.refresh_from_db()
        if run.status == AgentRun.Status.RUNNING:
            run.status = AgentRun.Status.FAILED
            run.error = str(exc)[:2000]
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
        return

    # The agent normally closes the run itself via ``finish_run``; if it did
    # not (older agent build, or a crash after the report), store what came back.
    run.refresh_from_db()
    if run.status == AgentRun.Status.RUNNING:
        run.report = body if isinstance(body, dict) else {}
        run.status = AgentRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=["report", "status", "finished_at"])
