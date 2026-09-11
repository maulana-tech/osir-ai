"""Composer URLs.

The composer UI lives in the Next.js console (``web/``) and talks to
``apps/webapi/routers/composer.py``. The page names below stay as redirects so
``reverse("composer:...")`` in emails, notifications and the remaining Django
templates keeps working; only the two byte-serving endpoints are still views.
"""

from django.urls import path

from apps.common.console import console

from . import views

app_name = "composer"

urlpatterns = [
    path("create/", console("/w/{workspace_id}/create"), name="create_landing"),
    # base.html (still used by the auth/OAuth pages) reverses these three.
    path("ideas/upload-media/", console("/w/{workspace_id}/create"), name="idea_upload_media"),
    path("ideas/create/", console("/w/{workspace_id}/create"), name="idea_create"),
    path("tags/create/", console("/w/{workspace_id}/create"), name="tag_create"),
    path("compose/", console("/w/{workspace_id}/compose"), name="compose"),
    path("compose/<uuid:post_id>/", console("/w/{workspace_id}/compose/{post_id}"), name="compose_edit"),
    # templates/calendar/partials/_delete_post_modal.html still reverses this.
    path("compose/<uuid:post_id>/delete/", console("/w/{workspace_id}/compose/{post_id}"), name="post_delete"),
    # Same-origin video bytes for the console's frame picker (proxied through /workspace/).
    path("compose/media-stream/<uuid:asset_id>/", views.media_stream, name="media_stream"),
    path("compose/media-filmstrip/<uuid:asset_id>/", views.media_filmstrip, name="media_filmstrip"),
    path("drafts/", console("/w/{workspace_id}/calendar?view=list&tab=drafts"), name="drafts_list"),
    path("categories/", console("/w/{workspace_id}/categories"), name="category_list"),
    path("templates/", console("/w/{workspace_id}/create?tab=templates"), name="template_list"),
    path(
        "templates/<uuid:template_id>/use/",
        console("/w/{workspace_id}/compose?template={template_id}"),
        name="use_template",
    ),
    path("import/csv/", console("/w/{workspace_id}/import"), name="csv_upload"),
    path("feeds/", console("/w/{workspace_id}/create?tab=feeds"), name="feed_list"),
]
