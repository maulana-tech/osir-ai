"""Workspace-scoped page data. Every route takes the workspace in the URL."""

from __future__ import annotations

import uuid

from django.db.models import Count, Q
from ninja import Router

from apps.composer.models import PlatformPost
from apps.inbox.models import InboxMessage
from apps.social_accounts.models import AnalyticsPlatformConfig, PlatformVisibility, SocialAccount
from apps.webapi.common import scoped

router = Router(tags=["workspaces"])


def _account(sa: SocialAccount) -> dict:
    return {
        "id": str(sa.id),
        "platform": sa.platform,
        "platform_label": sa.get_platform_display(),
        "name": sa.account_name,
        "handle": sa.account_handle,
        "avatar_url": sa.avatar_url,
        "connection_status": sa.connection_status,
        "last_error": sa.last_error,
        "queued_post_count": getattr(sa, "queued_post_count", 0),
        "auth_source": sa.auth_source,
    }


@router.get("/{workspace_id}/sidebar", summary="Navigation data for one workspace")
def sidebar(request, workspace_id: uuid.UUID):
    scoped(request, workspace_id)
    connected = list(
        SocialAccount.objects.for_workspace(workspace_id)
        .filter(connection_status=SocialAccount.ConnectionStatus.CONNECTED)
        .annotate(
            queued_post_count=Count("platform_posts", filter=Q(platform_posts__status=PlatformPost.Status.SCHEDULED))
        )
        .order_by("platform", "account_name")
    )
    unhealthy = list(
        SocialAccount.objects.for_workspace(workspace_id)
        .filter(
            connection_status__in=[
                SocialAccount.ConnectionStatus.DISCONNECTED,
                SocialAccount.ConnectionStatus.ERROR,
                SocialAccount.ConnectionStatus.TOKEN_EXPIRING,
            ]
        )
        .order_by("platform", "account_name")
    )
    connected_platforms = {sa.platform for sa in connected}
    return {
        "channels": [_account(sa) for sa in connected],
        "unhealthy_channels": [_account(sa) for sa in unhealthy],
        "connectable_platforms": [
            {"platform": p, "label": label}
            for p, label in PlatformVisibility.visible_choices()
            if p not in connected_platforms
        ],
        "analytics_enabled_platforms": sorted(AnalyticsPlatformConfig.enabled_platforms()),
        "unread_inbox_count": InboxMessage.objects.for_workspace(workspace_id)
        .filter(status=InboxMessage.Status.UNREAD)
        .count(),
        "pending_approvals": PlatformPost.objects.filter(
            post__workspace_id=workspace_id, status__in=["pending_review", "pending_client"]
        )
        .values("post_id")
        .distinct()
        .count(),
    }
