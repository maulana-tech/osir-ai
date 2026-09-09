"""Amazon Bedrock AgentCore Runtime entrypoint.

Invoke with a JSON payload:
    {"task": "inbox" | "calendar" | "digest" | "all", "dry_run": false}
    {"task": "command", "instruction": "Plan next week for the LinkedIn page", "run_id": "<optional AgentRun id>"}
Returns the structured run report(s). Scheduled by EventBridge Scheduler (see schedule/); console
commands arrive from Studio's ``invoke_agentcore`` task with a ``run_id`` to close.
"""

from __future__ import annotations

import logging

from bedrock_agentcore import BedrockAgentCoreApp

from osir_agent.loops import run_all, run_task

logging.basicConfig(level=logging.INFO)
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict, context=None) -> dict:
    task = str(payload.get("task", "inbox"))
    dry_run = payload.get("dry_run")
    # AgentCore's inspector and `agentcore invoke --prompt` send {"prompt": "..."}: treat it as a command.
    instruction = payload.get("instruction") or payload.get("prompt")
    if instruction and "task" not in payload:
        task = "command"
    if task == "all":
        return {"reports": [r.model_dump() for r in run_all(dry_run=dry_run)]}
    return run_task(task, instruction=instruction, run_id=payload.get("run_id"), dry_run=dry_run).model_dump()


if __name__ == "__main__":
    app.run()
