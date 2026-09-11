"""URL names for the inbox, kept alive for ``reverse()``; the pages live in the console (``web/``)."""

from django.urls import path

from apps.common.console import console

app_name = "inbox"

urlpatterns = [
    path("", console("/w/{workspace_id}/inbox"), name="feed"),
    path("<uuid:message_id>/", console("/w/{workspace_id}/inbox/{message_id}"), name="message_detail"),
    path("saved-replies/", console("/w/{workspace_id}/inbox/settings"), name="saved_replies"),
    path("sla-config/", console("/w/{workspace_id}/inbox/settings"), name="sla_config"),
]
