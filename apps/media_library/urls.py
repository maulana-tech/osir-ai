from django.urls import path

from apps.common.console import console

from . import views

app_name = "media_library"

# The library pages are rendered by the Next.js console; these names stay for
# ``reverse()``. Mutations and searches go through ``/api/web/workspaces/<id>/media``.
urlpatterns = [
    path("", console("/w/{workspace_id}/media"), name="index"),
    path("<uuid:asset_id>/", console("/w/{workspace_id}/media?open={asset_id}"), name="asset_detail"),
    path("<uuid:asset_id>/edit/", console("/w/{workspace_id}/media/{asset_id}/edit"), name="asset_edit"),
    path("<uuid:asset_id>/download/", views.asset_download, name="asset_download"),
]
