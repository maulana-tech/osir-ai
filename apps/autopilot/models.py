"""Records of what the autopilot agent did, so the console can show it.

One ``AgentRun`` per agent invocation. Scheduled loops record themselves
when they finish; on-demand commands are created ``pending`` by the
console, claimed by whichever runner picks them up (AgentCore via
``tasks.invoke_agentcore`` or ``run_local.py worker``), and finished by
the agent through the ``finish_run`` MCP tool.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.common.managers import WorkspaceScopedManager


class AgentRun(models.Model):
    class Task(models.TextChoices):
        INBOX = "inbox", "Inbox"
        CALENDAR = "calendar", "Calendar"
        DIGEST = "digest", "Digest"
        COMMAND = "command", "Command"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="agent_runs")
    task = models.CharField(max_length=20, choices=Task.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    dry_run = models.BooleanField(default=False)
    instruction = models.TextField(blank=True, default="", help_text="The human's request (command runs only).")
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_runs"
    )
    report = models.JSONField(default=dict, blank=True, help_text="The agent's structured RunReport.")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = WorkspaceScopedManager()

    class Meta:
        db_table = "autopilot_agent_run"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task} {self.status} ({self.created_at:%Y-%m-%d %H:%M})"
