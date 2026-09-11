"""URL names for analytics, kept alive for ``reverse()``; the pages live in the console (``web/``)."""

from django.urls import path

from apps.common.console import console

app_name = "analytics"

urlpatterns = [
    path("", console("/w/{workspace_id}/analytics"), name="index"),
    # The old post URL carries no account id, so the drawer can't be deep-linked; land on the index.
    path("post/<uuid:post_id>/", console("/w/{workspace_id}/analytics"), name="post_detail"),
    path("<uuid:account_id>/", console("/w/{workspace_id}/analytics/{account_id}"), name="account"),
]
