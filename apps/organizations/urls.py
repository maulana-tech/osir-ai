"""Retired Django organization pages, kept as redirects to the Next.js console.

The settings/workspaces/calendar pages are rendered by ``web/`` and served by
``apps/webapi/routers/admin.py`` + ``scheduling.py``; the URL names survive
for ``reverse()`` / ``{% url %}`` in the remaining server-rendered code.
"""

from django.urls import path

from apps.common.console import console

app_name = "organizations"

urlpatterns = [
    path("settings/", console("/org/settings"), name="settings"),
    path("workspaces/", console("/org/workspaces"), name="workspaces"),
    path("calendar/", console("/org/calendar"), name="cross_workspace_calendar"),
]
