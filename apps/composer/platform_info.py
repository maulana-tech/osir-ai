"""Live platform lookups the composer's per-account panels need."""

from __future__ import annotations

from apps.credentials.models import resolve_platform_credentials
from providers import get_provider


def _token(account, provider):
    token = account.oauth_access_token
    if account.token_expires_at and account.is_token_expiring_soon:
        token = account.refresh_oauth_token(provider)  # may raise
    return token


def pinterest_boards(workspace, account) -> list[dict]:
    """``[{id, name}]``. Raises RuntimeError with a person-facing message."""
    provider = get_provider("pinterest", resolve_platform_credentials("pinterest", workspace.organization_id))
    try:
        token = _token(account, provider)
    except Exception as exc:  # noqa: BLE001 - provider errors vary
        raise RuntimeError("Token refresh failed") from exc
    try:
        boards = provider.get_boards(token)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to fetch boards") from exc
    return [{"id": b.get("id"), "name": b.get("name")} for b in boards]


_UNAVAILABLE = {
    "available": False,
    "creator_nickname": "",
    "privacy_level_options": [],
    "comment_disabled": False,
    "duet_disabled": False,
    "stitch_disabled": False,
    "max_video_post_duration_sec": None,
}


def tiktok_creator_info(workspace, account) -> dict:
    """TikTok requires a fresh creator-info query before each post. Degrades to ``available: False``."""
    provider = get_provider("tiktok", resolve_platform_credentials("tiktok", workspace.organization_id))
    try:
        token = _token(account, provider)
    except Exception:  # noqa: BLE001
        return {**_UNAVAILABLE, "error": "Token refresh failed"}
    try:
        info = provider.query_creator_info(token)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return {**_UNAVAILABLE, "error": "Failed to fetch creator info"}
    return {
        "available": True,
        "creator_nickname": info.get("creator_nickname", ""),
        "privacy_level_options": info.get("privacy_level_options") or [],
        "comment_disabled": bool(info.get("comment_disabled")),
        "duet_disabled": bool(info.get("duet_disabled")),
        "stitch_disabled": bool(info.get("stitch_disabled")),
        "max_video_post_duration_sec": info.get("max_video_post_duration_sec"),
    }
