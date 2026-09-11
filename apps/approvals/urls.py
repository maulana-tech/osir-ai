"""URL names for approval actions, kept alive for ``reverse()``/``{% url %}``.

The actions themselves live in the web API (``apps/webapi/routers/approvals.py``)
and the Agent API; these names are still referenced by
``templates/approvals/partials/_approval_row.html`` and the calendar's publish tab,
so they redirect to the console's approvals page.
"""

from django.urls import path

from apps.common.console import console

app_name = "approvals"

_approvals = console("/w/{workspace_id}/approvals")

urlpatterns = [
    path("approvals/<uuid:post_id>/approve/", _approvals, name="approve"),
    path("approvals/<uuid:post_id>/request-changes/", _approvals, name="request_changes"),
    path("approvals/<uuid:post_id>/reject/", _approvals, name="reject"),
    path("approvals/<uuid:post_id>/resume/", _approvals, name="resume"),
    path("approvals/bulk/", _approvals, name="bulk_action"),
    path("approvals/<uuid:post_id>/versions/", _approvals, name="version_diff"),
]
