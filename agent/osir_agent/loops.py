"""The background loops and the on-demand command. Each is one Strands agent invocation over Studio's MCP tools.

Every run is recorded back in Studio (``record_run`` / ``finish_run``) so
the console can show what happened, including failures.
"""

from __future__ import annotations

import json
import logging
import time
import traceback

from strands import Agent
from strands.models import BedrockModel

from .config import Settings, load_settings
from .prompts import TASKS, system_prompt
from .report import RunReport
from .studio import fetch_policy, select_tools, studio_client

logger = logging.getLogger("osir_agent")


def _call(client, name: str, **arguments) -> dict:
    result = client.call_tool_sync(tool_use_id=f"runner-{name}", name=name, arguments=arguments)
    return json.loads(result["content"][0]["text"])


def _run_with_client(client, task: str, instruction: str | None, settings: Settings, dry_run: bool) -> RunReport:
    prompt = TASKS[task](settings, instruction)
    policy = fetch_policy(client)
    if policy.get("agent_autonomy") == "off" and not dry_run:
        # The human turned the dial to off: observe only, exactly like dry-run.
        dry_run = True
    tools = select_tools(client.list_tools_sync(), dry_run=dry_run, policy=policy)
    logger.info("task=%s dry_run=%s autonomy=%s tools=%d", task, dry_run, policy.get("agent_autonomy"), len(tools))

    model = BedrockModel(model_id=settings.model_id, region_name=settings.region, temperature=0.2)
    agent = Agent(model=model, tools=tools, system_prompt=system_prompt(settings, policy), callback_handler=None)
    if dry_run:
        prompt += "\n\nDRY RUN: write tools are unavailable. Describe each action you WOULD take instead."
    result = agent(prompt, structured_output_model=RunReport)

    report: RunReport = result.structured_output
    report.task = task
    report.dry_run = dry_run
    return report


def run_task(
    task: str,
    *,
    instruction: str | None = None,
    run_id: str | None = None,
    settings: Settings | None = None,
    dry_run: bool | None = None,
) -> RunReport:
    """Run one task and record it in Studio.

    ``run_id`` is set when the run was created by the console (a pending
    ``AgentRun``); otherwise a new record is written at the end.
    """
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {sorted(TASKS)}")
    settings = settings or load_settings()
    dry_run = settings.dry_run if dry_run is None else dry_run

    client = studio_client(settings)
    with client:
        try:
            report = _run_with_client(client, task, instruction, settings, dry_run)
        except Exception as exc:
            logger.exception("run failed task=%s", task)
            error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}"
            if run_id:
                _call(client, "finish_run", run_id=run_id, error=error)
            else:
                _call(client, "record_run", task=task, dry_run=dry_run, instruction=instruction or "", error=error)
            raise
        payload = report.model_dump()
        if run_id:
            _call(client, "finish_run", run_id=run_id, report=payload)
        else:
            _call(client, "record_run", task=task, dry_run=dry_run, instruction=instruction or "", report=payload)
    return report


def run_all(**kwargs) -> list[RunReport]:
    return [run_task(t, **kwargs) for t in ("inbox", "calendar")]


def work_pending(*, settings: Settings | None = None, poll_seconds: int = 10, once: bool = False) -> None:
    """Local runner for console commands: claim pending runs and execute them.

    This is what stands in for AgentCore when ``AGENT_RUNTIME_ARN`` is not
    configured on the Studio side.
    """
    settings = settings or load_settings()
    while True:
        with studio_client(settings) as client:
            run = _call(client, "claim_pending_run")["run"]
        if run:
            logger.info("claimed run %s: %s", run["id"], run["instruction"][:80])
            try:
                run_task(run["task"], instruction=run["instruction"], run_id=run["id"], dry_run=run["dry_run"])
            except Exception:
                logger.exception("run %s failed; recorded in Studio, moving on", run["id"])
            continue
        if once:
            return
        time.sleep(poll_seconds)
