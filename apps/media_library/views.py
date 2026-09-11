"""Media library file downloads.

The library pages and their HTMX/JSON endpoints live in the Next.js console and
``apps/webapi/routers/media.py``; only the file responses the console links to
remain here.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET

from apps.members.decorators import require_org_role

from .models import MediaAsset


def _get_workspace_or_404(request, workspace_id):
    """Get workspace and verify the user has access via the RBAC middleware."""
    if not request.workspace or str(request.workspace.id) != str(workspace_id):
        raise Http404
    return request.workspace


def _file_response(asset):
    if getattr(settings, "STORAGE_BACKEND", "local") == "s3":
        # For S3, redirect to a signed URL
        return redirect(asset.file.url)
    return FileResponse(asset.file.open("rb"), as_attachment=True, filename=asset.original_filename)


@login_required
@require_GET
def asset_download(request, workspace_id, asset_id):
    workspace = _get_workspace_or_404(request, workspace_id)
    asset = get_object_or_404(
        MediaAsset.objects.for_workspace_with_shared(
            workspace_id=workspace.id,
            organization_id=workspace.organization_id,
        ),
        pk=asset_id,
    )
    return _file_response(asset)


@login_required
@require_org_role("member")
@require_GET
def shared_asset_download(request, asset_id):
    org = request.org
    if not org:
        raise Http404
    asset = get_object_or_404(MediaAsset.objects.shared_only(org.id), pk=asset_id)
    return _file_response(asset)
