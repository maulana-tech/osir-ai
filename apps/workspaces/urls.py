from django.urls import path

from apps.common.console import console

app_name = "workspaces"

urlpatterns = [
    path("", console("/org/workspaces"), name="list"),
    path("<uuid:workspace_id>/settings/", console("/w/{workspace_id}/settings"), name="settings"),
    path("<uuid:workspace_id>/settings/approvals/", console("/w/{workspace_id}/settings"), name="approvals_settings"),
]
