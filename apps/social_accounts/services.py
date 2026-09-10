"""Account lifecycle operations shared by the HTMX views and the web API."""

from __future__ import annotations

import logging

from django.db.models import Count

from apps.credentials import composio

from .models import SocialAccount
from .provider_factory import _get_provider_for_platform
from .webhooks import subscribe_account_webhooks, unsubscribe_account_webhooks

logger = logging.getLogger(__name__)


def disconnect_account(account: SocialAccount, org_id) -> str:
    """Revoke, unsubscribe, drop orphaned posts, delete. Returns the display name."""
    from apps.composer.models import PlatformPost, Post

    # Stop the platform pushing us this account's activity before we drop the
    # token that would let us unsubscribe.
    if account.oauth_access_token:
        unsubscribe_account_webhooks(account)
    if account.composio_connected_account_id:
        composio.delete_connection(account.composio_connected_account_id)
    try:
        provider = _get_provider_for_platform(account.platform, org_id)
        if account.oauth_access_token:
            provider.revoke_token(account.oauth_access_token)
    except Exception:
        logger.warning("Failed to revoke token for %s, proceeding with disconnect", account)

    # Posts that ONLY target this account would be fully orphaned; multi-platform
    # posts keep their other targets via the FK cascade.
    orphan_post_ids = list(
        PlatformPost.objects.filter(social_account=account)
        .values("post_id")
        .annotate(total_platforms=Count("post__platform_posts"))
        .filter(total_platforms=1)
        .values_list("post_id", flat=True)
    )
    if orphan_post_ids:
        Post.objects.filter(id__in=orphan_post_ids).delete()

    name = account.account_name or account.account_handle
    account.delete()
    return name


def retry_webhooks(account: SocialAccount) -> bool:
    """One explicit re-subscription attempt; resets the automatic retry budget first.

    Raises ``ValueError`` when the connection itself is unhealthy: a dead
    connection cannot carry a subscription, reconnect first.
    """
    if account.needs_reconnect:
        raise ValueError(f"Reconnect {account.display_label} first — its connection isn't healthy.")
    SocialAccount.objects.filter(pk=account.pk).update(webhook_retry_count=0)
    account.webhook_retry_count = 0
    subscribed = subscribe_account_webhooks(account)
    account.refresh_from_db()
    return subscribed
