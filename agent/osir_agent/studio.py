"""Connection to Osir AI Studio's MCP server.

Studio already exposes everything the agent needs as MCP tools behind a
workspace-scoped API key, so the agent has no Studio-specific code of its
own: it discovers the tools at runtime and the permission checks happen
server-side on every call.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

from .config import Settings

# Tools that change something a human or a customer can see. Hidden in dry-run
# so the agent can only observe and describe what it would have done.
WRITE_TOOLS = frozenset(
    {
        "reply_to_inbox_message",
        "triage_inbox_message",
        "create_draft",
        "schedule_post",
        "schedule_draft",
        "cancel_post",
        "submit_for_approval",
        "notify_team",
        "upload_media",
        "request_media_upload",
        "finalize_media_upload",
        # Runner bookkeeping: the model never calls these.
        "record_run",
        "claim_pending_run",
        "finish_run",
    }
)

# Tools that put content on the publisher's queue. Only offered when the
# workspace dial says autopilot, the approval workflow allows direct
# scheduling, and the key itself may publish.
SCHEDULE_TOOLS = frozenset({"schedule_post", "schedule_draft", "cancel_post"})


def studio_client(settings: Settings) -> MCPClient:
    return MCPClient(
        lambda: streamablehttp_client(
            settings.mcp_url,
            headers={"Authorization": f"Bearer {settings.studio_api_key}"},
            timeout=timedelta(seconds=60),
        )
    )


def fetch_policy(client: MCPClient) -> dict[str, Any]:
    """Call ``get_workspace_policy`` once, before the model sees any tool."""
    result = client.call_tool_sync(tool_use_id="policy", name="get_workspace_policy", arguments={})
    return json.loads(result["content"][0]["text"])


def may_schedule(policy: dict[str, Any]) -> bool:
    return bool(
        policy.get("agent_autonomy") == "autopilot"
        and policy.get("direct_scheduling_allowed")
        and policy.get("can_publish")
    )


def select_tools(tools: list, *, dry_run: bool, policy: dict[str, Any] | None = None) -> list:
    """Filter the discovered tools by run mode and workspace policy.

    ``tools`` come from ``MCPClient.list_tools_sync()``. Dry-run drops every
    write tool; a non-autopilot policy drops the scheduling tools.
    """
    hidden: set[str] = set()
    if dry_run:
        hidden |= WRITE_TOOLS
    if policy is not None and not may_schedule(policy):
        hidden |= SCHEDULE_TOOLS
    return [t for t in tools if t.tool_name not in hidden]
