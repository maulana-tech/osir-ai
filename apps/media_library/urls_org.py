from django.urls import path

from apps.common.console import console

from . import views

app_name = "media_library_org"

# The shared library pages are rendered by the Next.js console; these names stay
# for ``reverse()``. Mutations and searches go through ``/api/web/org/media``.
urlpatterns = [
    path("shared/", console("/org/media"), name="shared_index"),
    path("shared/<uuid:asset_id>/", console("/org/media?open={asset_id}"), name="shared_asset_detail"),
    path("shared/<uuid:asset_id>/edit/", console("/org/media/{asset_id}/edit"), name="shared_asset_edit"),
    path("shared/<uuid:asset_id>/download/", views.shared_asset_download, name="shared_asset_download"),
]
