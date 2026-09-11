"""Retired Django calendar pages, kept as redirects to the Next.js console.

The templates and views are gone (the console at ``web/`` renders these pages
and talks to ``apps/webapi``); the URL names survive so ``reverse()`` and
``{% url %}`` in the remaining server-rendered code keep working. The slot
mutation names stay only because ``templates/social_accounts/partials/
_posting_slots_grid.html`` still reverses them.
"""

from django.urls import path

from apps.common.console import console

app_name = "calendar"

_CAL = "/w/{workspace_id}/calendar"
_SLOTS = f"{_CAL}/slots"

urlpatterns = [
    path("", console(_CAL), name="calendar"),
    path("publish/queue/", console(f"{_CAL}?view=list&tab=queue"), name="publish_tab_queue"),
    path("publish/drafts/", console(f"{_CAL}?view=list&tab=drafts"), name="publish_tab_drafts"),
    path("publish/approvals/", console(f"{_CAL}?view=list&tab=approvals"), name="publish_tab_approvals"),
    path("publish/sent/", console(f"{_CAL}?view=list&tab=sent"), name="publish_tab_sent"),
    path("posting-slots/", console(_SLOTS), name="posting_slots"),
    path("posting-slots/save/", console(_SLOTS), name="save_posting_slot"),
    path("posting-slots/grid/", console(_SLOTS), name="account_slots_partial"),
    path("posting-slots/toggle-day/", console(_SLOTS), name="toggle_posting_slot_day"),
    path("posting-slots/<uuid:slot_id>/delete/", console(_SLOTS), name="delete_posting_slot"),
    path("posting-slots/<uuid:slot_id>/update/", console(_SLOTS), name="update_posting_slot"),
    path("queues/", console(f"{_CAL}/queues"), name="queue_list"),
    path("queues/<uuid:queue_id>/", console(f"{_CAL}/queues/{{queue_id}}"), name="queue_detail"),
]
