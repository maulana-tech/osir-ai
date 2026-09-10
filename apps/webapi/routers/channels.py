"""Connected channels for one workspace. Connecting itself stays a Django redirect flow."""

from __future__ import annotations

import uuid

from ninja import Router
from ninja.errors import HttpError

from apps.credentials import composio
from apps.credentials.models import PlatformCredential
from apps.social_accounts import services
from apps.social_accounts.models import PlatformVisibility, SocialAccount
from apps.social_accounts.views import _get_configured_platforms
from apps.webapi.common import require_perm, scoped

router = Router(tags=["channels"])


def _account(a: SocialAccount) -> dict:
    return {
        "id": str(a.id),
        "platform": a.platform,
        "platform_label": a.get_platform_display(),
        "name": a.account_name,
        "handle": a.account_handle,
        "avatar_url": a.avatar_url,
        "follower_count": a.follower_count,
        "connection_status": a.connection_status,
        "needs_reconnect": a.needs_reconnect,
        "last_error": a.last_error,
        "last_health_check_at": a.last_health_check_at.isoformat() if a.last_health_check_at else None,
        "webhooks_active": a.webhooks_active,
        "webhook_needs_reconnect": a.webhook_needs_reconnect,
        "webhook_error": a.webhook_error,
        "analytics_needs_reconnect": a.analytics_needs_reconnect,
        "auth_source": a.auth_source,
        "posting_slot_count": getattr(a, "slot_count", None),
        "connected_at": a.connected_at.isoformat(),
    }


@router.get("/{workspace_id}/channels", summary="Connected accounts and what can still be connected")
def channels(request, workspace_id: uuid.UUID):
    membership = scoped(request, workspace_id)
    org_id = membership.workspace.organization_id
    accounts = list(SocialAccount.objects.for_workspace(workspace_id).order_by("platform", "account_name"))
    configured = _get_configured_platforms(org_id)
    via_composio = composio.available_platforms() - configured
    labels = dict(PlatformCredential.Platform.choices)
    return {
        "accounts": [_account(a) for a in accounts],
        "platforms": [
            {
                "platform": p,
                "label": label,
                "configured": p in configured,
                "via_composio": p in via_composio,
            }
            for p, label in PlatformVisibility.visible_choices()
        ],
        "platform_labels": labels,
        "can_manage": bool(membership.effective_permissions.get("manage_social_accounts")),
    }


def _managed(request, workspace_id, account_id) -> SocialAccount:
    membership = scoped(request, workspace_id)
    require_perm(membership, "manage_social_accounts")
    try:
        return SocialAccount.objects.for_workspace(workspace_id).get(id=account_id)
    except SocialAccount.DoesNotExist as exc:
        raise HttpError(404, "Account not found") from exc


@router.post("/{workspace_id}/channels/{uuid:account_id}/disconnect", summary="Disconnect an account")
def disconnect(request, workspace_id: uuid.UUID, account_id: uuid.UUID):
    account = _managed(request, workspace_id, account_id)
    name = services.disconnect_account(account, request.workspace.organization_id)
    return {"disconnected": name}


@router.post("/{workspace_id}/channels/{uuid:account_id}/retry-webhooks", summary="Retry real-time subscription")
def retry_webhooks(request, workspace_id: uuid.UUID, account_id: uuid.UUID):
    account = _managed(request, workspace_id, account_id)
    try:
        ok = services.retry_webhooks(account)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return {"subscribed": ok, "account": _account(account)}
