"""The checks that must never break: dry-run hides every write tool, and only an autopilot workspace
with a publishing key ever sees the scheduling tools."""

from types import SimpleNamespace

from osir_agent.prompts import TASKS, system_prompt
from osir_agent.studio import SCHEDULE_TOOLS, WRITE_TOOLS, may_schedule, select_tools

ALL = [
    "list_accounts",
    "list_inbox_messages",
    "get_inbox_message",
    "reply_to_inbox_message",
    "triage_inbox_message",
    "create_draft",
    "submit_for_approval",
    "notify_team",
    "get_schedule",
    "schedule_post",
    "schedule_draft",
    "cancel_post",
    "get_workspace_policy",
    "record_run",
    "finish_run",
]
AUTOPILOT = {"agent_autonomy": "autopilot", "direct_scheduling_allowed": True, "can_publish": True}


def _tools():
    return [SimpleNamespace(tool_name=n) for n in ALL]


def _names(tools):
    return {t.tool_name for t in tools}


def test_dry_run_keeps_only_reads():
    kept = _names(select_tools(_tools(), dry_run=True))
    assert kept == {"list_accounts", "list_inbox_messages", "get_inbox_message", "get_schedule", "get_workspace_policy"}
    assert not kept & WRITE_TOOLS


def test_draft_only_policy_hides_scheduling():
    policy = {**AUTOPILOT, "agent_autonomy": "draft_only"}
    kept = _names(select_tools(_tools(), dry_run=False, policy=policy))
    assert not kept & SCHEDULE_TOOLS
    assert {"create_draft", "submit_for_approval", "reply_to_inbox_message"} <= kept


def test_autopilot_needs_all_three_conditions():
    assert may_schedule(AUTOPILOT)
    assert not may_schedule({**AUTOPILOT, "direct_scheduling_allowed": False})
    assert not may_schedule({**AUTOPILOT, "can_publish": False})
    assert _names(select_tools(_tools(), dry_run=False, policy=AUTOPILOT)) >= SCHEDULE_TOOLS


def test_prompts_render_for_every_task():
    settings = SimpleNamespace(brand_voice="", max_replies=5, max_drafts=2)
    assert "autopilot" in system_prompt(settings, AUTOPILOT)
    for name, build in TASKS.items():
        text = build(settings, "Plan next week for LinkedIn")
        assert "structured report" in text, name
