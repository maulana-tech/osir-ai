"""Composio as the fallback OAuth broker.

An org's own developer app (``PlatformCredential`` or ``.env``) always
wins. When it has none for a platform and ``COMPOSIO_API_KEY`` plus a
Composio auth config for that platform are set, the connect button runs
Composio's hosted OAuth instead. Composio never exposes the resulting
tokens, so accounts connected this way call the platform through
Composio's credential-injecting proxy (see ``providers.base.SocialProvider._request``).

Only platforms with a Composio-managed OAuth toolkit are eligible.
"""

from __future__ import annotations

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://backend.composio.dev/api/v3.1"
TIMEOUT = 30.0

# Studio platform → Composio toolkit slug. Platforms missing here have no
# Composio-managed OAuth (TikTok requires your own app; Threads, Bluesky,
# Mastodon, Google Business and DEV.to have no toolkit or need none).
TOOLKITS: dict[str, str] = {
    "linkedin_personal": "LINKEDIN",
    "linkedin_company": "LINKEDIN",
    "facebook": "FACEBOOK",
    "instagram": "FACEBOOK",
    "instagram_login": "INSTAGRAM",
    "youtube": "YOUTUBE",
    "pinterest": "PINTEREST",
}


class ComposioError(Exception):
    pass


def api_key() -> str:
    return getattr(settings, "COMPOSIO_API_KEY", "") or ""


def auth_config_id(platform: str) -> str:
    return (getattr(settings, "COMPOSIO_AUTH_CONFIGS", {}) or {}).get(platform, "")


def is_available(platform: str) -> bool:
    return bool(api_key() and platform in TOOLKITS and auth_config_id(platform))


def available_platforms() -> set[str]:
    return {p for p in TOOLKITS if is_available(p)}


def _post(path: str, payload: dict) -> dict:
    resp = httpx.post(f"{BASE_URL}{path}", json=payload, headers={"x-api-key": api_key()}, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise ComposioError(f"Composio {path} failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def _get(path: str) -> dict:
    resp = httpx.get(f"{BASE_URL}{path}", headers={"x-api-key": api_key()}, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise ComposioError(f"Composio {path} failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def create_link(*, platform: str, user_id: str, callback_url: str) -> tuple[str, str]:
    """Start hosted auth. Returns ``(connected_account_id, redirect_url)``."""
    body = _post(
        "/connected_accounts/link",
        {"auth_config_id": auth_config_id(platform), "user_id": user_id, "callback_url": callback_url},
    )
    try:
        return body["connected_account_id"], body["redirect_url"]
    except KeyError as exc:
        raise ComposioError(f"Unexpected link response: {sorted(body)}") from exc


def connection_status(connected_account_id: str) -> str:
    """``ACTIVE`` once the user finished the hosted flow."""
    return str(_get(f"/connected_accounts/{connected_account_id}").get("status", "")).upper()


def delete_connection(connected_account_id: str) -> None:
    try:
        resp = httpx.delete(
            f"{BASE_URL}/connected_accounts/{connected_account_id}",
            headers={"x-api-key": api_key()},
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400 and resp.status_code != 404:
            logger.warning("Composio delete %s -> %s", connected_account_id, resp.status_code)
    except httpx.HTTPError:
        logger.exception("Composio delete failed for %s", connected_account_id)


def proxy_credentials(connected_account_id: str) -> dict:
    """Credential entries that make a provider route its HTTP through Composio."""
    return {"composio_api_key": api_key(), "composio_connected_account_id": connected_account_id}
