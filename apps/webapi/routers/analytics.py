"""Channel analytics for the web UI, assembled from the same service layer as the templates."""

from __future__ import annotations

import dataclasses
import uuid

from django.db.models import QuerySet
from ninja import Router
from ninja.errors import HttpError

from apps.analytics import services
from apps.analytics.metrics import PLATFORM_PRIMARY
from apps.analytics.models import AccountInsightsSnapshot
from apps.composer.models import PlatformPost
from apps.social_accounts.models import AnalyticsPlatformConfig, SocialAccount
from apps.webapi.common import require_perm, scoped

router = Router(tags=["analytics"])

RANGE_CHOICES = (7, 30, 90)


def _accounts(workspace_id) -> list[dict]:
    enabled = AnalyticsPlatformConfig.enabled_platforms()
    qs: QuerySet[SocialAccount] = SocialAccount.objects.for_workspace(workspace_id).filter(
        connection_status=SocialAccount.ConnectionStatus.CONNECTED
    )
    out = []
    for a in qs.order_by("platform", "account_name"):
        verdict = services.analytics_availability(a.platform, enabled)
        out.append(
            {
                "id": str(a.id),
                "platform": a.platform,
                "platform_label": a.get_platform_display(),
                "name": a.account_name,
                "avatar_url": a.avatar_url,
                "follower_count": a.follower_count,
                "analytics_available": verdict is None,
                "unavailable_reason": verdict.message if verdict else None,
                "disabled_by_admin": bool(verdict and verdict.cause == services.CAUSE_DISABLED),
                "needs_reconnect": a.analytics_needs_reconnect,
            }
        )
    return out


def _derived(d) -> dict | None:
    return dataclasses.asdict(d) if d is not None else None


def _card(c: dict) -> dict:
    return {"metric": c["metric"], "label": c["label"], "derived": _derived(c["derived"])}


def _table(t: dict) -> dict:
    return {
        **{k: v for k, v in t.items() if k != "rows"},
        "rows": [
            {
                "platform_post_id": str(r["post"].id),
                "post_id": str(r["post"].post_id),
                "caption": r["caption"],
                "date": r["date"],
                "days_ago": r["days_ago"],
                "media_kind": r["media_kind"],
                "media_preview": r["media_preview"],
                "stats": r["stats"],
            }
            for r in t["rows"]
        ],
    }


@router.get("/{workspace_id}/analytics", summary="Accounts that have analytics, and which to open first")
def index(request, workspace_id: uuid.UUID):
    membership = scoped(request, workspace_id)
    require_perm(membership, "view_analytics")
    accounts = _accounts(workspace_id)
    preferred = next((a for a in accounts if a["analytics_available"]), accounts[0] if accounts else None)
    return {
        "enabled": bool(AnalyticsPlatformConfig.enabled_platforms()),
        "accounts": accounts,
        "preferred_account_id": preferred["id"] if preferred else None,
    }


def _int(value: str | None, choices, default):
    try:
        n = int(value or default)
    except (TypeError, ValueError):
        return default
    return n if n in choices else default


@router.get("/{workspace_id}/analytics/accounts/{uuid:account_id}", summary="One channel's analytics")
def account(
    request,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    range: str = "30",  # noqa: A002 - mirrors the ``?range=`` query param the templates use
    chart_metric: str | None = None,
    table_range: str | None = None,
    sort: str | None = None,
    dir: str = "desc",  # noqa: A002
    type: str = "all",  # noqa: A002
    page: int = 1,
):
    membership = scoped(request, workspace_id)
    require_perm(membership, "view_analytics")
    accounts = _accounts(workspace_id)
    entry = next((a for a in accounts if a["id"] == str(account_id)), None)
    if entry is None:
        raise HttpError(404, "Account not found")
    acct = SocialAccount.objects.get(id=account_id)
    days = _int(range, RANGE_CHOICES, 30)
    days_filter = None if table_range in ("", "all") else _int(table_range, RANGE_CHOICES, days)
    page = max(1, page)

    has_any_post = PlatformPost.objects.filter(social_account=acct, status=PlatformPost.Status.PUBLISHED).exists()
    is_fresh = not has_any_post and not AccountInsightsSnapshot.objects.filter(social_account=acct).exists()
    payload: dict = {
        "account": entry,
        "accounts": accounts,
        "days": days,
        "range_choices": list(RANGE_CHOICES),
        "is_fresh": is_fresh,
    }

    if not entry["analytics_available"]:
        table = services.all_posts_for(
            acct, days_filter=days_filter, sort_key="date", sort_dir=dir, type_filter=type, page=page
        )
        table["metric_labels"] = []
        payload["table"] = _table(table)
        return payload
    if is_fresh:
        return payload

    bundle = services.account_analytics_bundle(acct, days)
    series_map = bundle["series_map"]
    chart = services.hero_chart_data(acct, days, metric=chart_metric, series_map=series_map)
    engagement = services.engagement_card(acct, days, series_map=series_map)
    table = services.all_posts_for(
        acct,
        days_filter=days_filter,
        sort_key=sort or PLATFORM_PRIMARY.get(acct.platform),
        sort_dir=dir,
        type_filter=type,
        page=page,
    )
    payload.update(
        {
            "follower_growth": _derived(services.follower_growth(acct, days, series_map=series_map)),
            "hero_cards": [_card(c) for c in services.hero_cards(acct, days, series_map=series_map)],
            "engagement": (
                {"rate": _derived(engagement["rate"]), "parts": [_card(c) for c in engagement["parts"]]}
                if engagement
                else None
            ),
            "chart": {**{k: v for k, v in chart.items() if k != "derived"}, "derived": _derived(chart["derived"])},
            "table": _table(table),
        }
    )
    return payload
