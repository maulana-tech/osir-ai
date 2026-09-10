"""Organization settings and deletion, shared by the HTMX views and the web API."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import available_timezones

from django.utils import timezone

DELETION_GRACE = timedelta(days=14)
_TASK_NAME = "apps.organizations.tasks.execute_scheduled_org_deletion"


def update_name(org, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Organization name cannot be empty.")
    org.name = name
    org.save(update_fields=["name"])


def update_timezone(org, tz: str) -> None:
    tz = tz.strip()
    if tz not in available_timezones():
        raise ValueError("Invalid timezone.")
    org.default_timezone = tz
    org.save(update_fields=["default_timezone"])


def _drop_scheduled_task(org) -> None:
    from background_task.models import Task

    Task.objects.filter(task_name=_TASK_NAME, task_params__contains=str(org.id)).delete()


def schedule_deletion(org) -> None:
    """Queue the hard delete after the grace period."""
    from apps.organizations.tasks import execute_scheduled_org_deletion

    org.deletion_requested_at = timezone.now()
    org.deletion_scheduled_for = timezone.now() + DELETION_GRACE
    org.save(update_fields=["deletion_requested_at", "deletion_scheduled_for"])
    execute_scheduled_org_deletion(str(org.id), schedule=DELETION_GRACE)


def cancel_deletion(org) -> None:
    _drop_scheduled_task(org)
    org.deletion_requested_at = None
    org.deletion_scheduled_for = None
    org.save(update_fields=["deletion_requested_at", "deletion_scheduled_for"])


def delete_now(org, requesting_user) -> None:
    _drop_scheduled_task(org)
    org.hard_delete(requesting_user=requesting_user)
