"""Structured run report every loop must end with.

Machine-readable so the scheduler, the logs, and the demo dashboard can
show what the agent did without parsing prose.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Action(BaseModel):
    kind: str = Field(description="replied | resolved | escalated | drafted | submitted | notified | skipped")
    target_id: str = Field(default="", description="Studio id of the message/post/idea acted on, if any")
    summary: str = Field(description="One sentence: what was done and why")


class RunReport(BaseModel):
    task: str = Field(description="inbox | calendar | digest")
    dry_run: bool = Field(default=False)
    actions: list[Action] = Field(default_factory=list)
    decisions_for_humans: list[str] = Field(
        default_factory=list,
        description="Things a person must decide; each already sent via notify_team unless dry_run",
    )
    notes: str = Field(default="", description="Anything worth logging that is not an action")
