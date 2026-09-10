"""Unsplash stock photos: server-side search proxy and import into the media library."""

from __future__ import annotations

import contextlib

import httpx
from django.conf import settings
from django.core.files.base import ContentFile

API_BASE = "https://api.unsplash.com"
IMAGE_HOST = "https://images.unsplash.com/"
NOT_CONFIGURED = "Unsplash is not configured. Add UNSPLASH_ACCESS_KEY to your environment to enable stock-photo search."
MAX_IMPORT = 10
MAX_IMAGE_BYTES = 15 * 1024 * 1024


class UnsplashError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def enabled() -> bool:
    return bool(settings.UNSPLASH_ACCESS_KEY)


def _s(value) -> str:
    """Coerce an external/client JSON field to a string (null / numbers → '')."""
    return value if isinstance(value, str) else ""


def search(query: str) -> dict:
    """``{"results": [...], "total": n}`` trimmed to what the picker needs. Raises UnsplashError."""
    if not enabled():
        raise UnsplashError(503, NOT_CONFIGURED)
    query = (query or "").strip()
    if not query:
        raise UnsplashError(400, "Missing search query")
    try:
        resp = httpx.get(
            f"{API_BASE}/search/photos",
            params={"query": query, "page": 1, "per_page": 24},
            headers={"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}", "Accept-Version": "v1"},
            timeout=10.0,
        )
    except httpx.RequestError as exc:
        raise UnsplashError(502, "Could not reach Unsplash. Try again.") from exc
    if resp.status_code in (401, 403):
        raise UnsplashError(502, "Unsplash rejected the API key. Check UNSPLASH_ACCESS_KEY.")
    if resp.status_code == 429:
        raise UnsplashError(429, "Unsplash rate limit reached. Try again in a few minutes.")
    if resp.status_code != 200:
        raise UnsplashError(502, "Unsplash search failed. Try again.")
    try:
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected Unsplash response shape")
        results = [
            {
                "id": p["id"],
                "thumb": p["urls"]["small"],
                "full": p["urls"]["regular"],
                "width": p.get("width"),
                "height": p.get("height"),
                "color": p.get("color"),
                "alt": p.get("alt_description") or p.get("description") or "",
                "photographer": p["user"]["name"],
                "photographer_url": p["user"]["links"]["html"],
                "photo_url": p["links"]["html"],
                "download_location": p["links"]["download_location"],
            }
            for p in data.get("results", [])
        ]
        return {"results": results, "total": data.get("total", 0)}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise UnsplashError(502, "Unexpected response from Unsplash. Try again.") from exc


def import_photos(workspace, user, photos) -> tuple[list, int]:
    """Download ``photos`` into the workspace library. Returns ``(assets, failed_count)``.

    Registers each download with Unsplash first (their guidelines), only ever
    fetches from Unsplash hosts, caps the body size, and enforces the storage
    quota. Raises UnsplashError (503 not configured, 400 bad input, 413 quota,
    502 nothing imported).
    """
    from apps.media_library.models import MediaAsset
    from apps.media_library.quotas import StorageQuotaExceededError, enforce_storage_quota

    if not enabled():
        raise UnsplashError(503, NOT_CONFIGURED)
    if not isinstance(photos, list) or not photos:
        raise UnsplashError(400, "No photos selected")
    if len(photos) > MAX_IMPORT:
        raise UnsplashError(400, f"Select at most {MAX_IMPORT} photos per import.")

    auth = {"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"}
    assets: list = []
    failed = 0
    quota_exceeded = False
    # follow_redirects is OFF so the host allowlist can't be bounced to an internal address.
    with httpx.Client(follow_redirects=False, timeout=30.0) as client:
        for photo in photos:
            if not isinstance(photo, dict):
                failed += 1
                continue
            photo_id = _s(photo.get("id")).strip()
            download_location = _s(photo.get("download_location"))
            if not photo_id or not download_location.startswith(f"{API_BASE}/"):
                failed += 1
                continue
            content = None
            content_type = ""
            try:
                dl = client.get(download_location, headers=auth, timeout=10.0)
                image_url = ""
                if dl.status_code == 200:
                    with contextlib.suppress(ValueError, AttributeError):
                        image_url = _s(dl.json().get("url"))
                image_url = image_url or _s(photo.get("full"))
                if not image_url.startswith(IMAGE_HOST):
                    failed += 1
                    continue
                with client.stream("GET", image_url) as img:
                    content_type = img.headers.get("content-type", "")
                    declared = img.headers.get("content-length", "")
                    if (
                        img.status_code != 200
                        or not content_type.startswith("image/")
                        or (declared.isdigit() and int(declared) > MAX_IMAGE_BYTES)
                    ):
                        failed += 1
                        continue
                    buf = bytearray()
                    for chunk in img.iter_bytes():
                        buf += chunk
                        if len(buf) > MAX_IMAGE_BYTES:
                            break
                    if len(buf) > MAX_IMAGE_BYTES:
                        failed += 1
                        continue
                    content = bytes(buf)
            except httpx.HTTPError:
                failed += 1
                continue
            try:
                enforce_storage_quota(workspace.organization, len(content))
            except StorageQuotaExceededError:
                quota_exceeded = True
                break
            filename = f"unsplash-{photo_id}.jpg"
            assets.append(
                MediaAsset.objects.create(
                    organization=workspace.organization,
                    workspace=workspace,
                    uploaded_by=user,
                    file=ContentFile(content, name=filename),
                    filename=filename,
                    media_type=MediaAsset.MediaType.IMAGE,
                    mime_type=content_type,
                    file_size=len(content),
                    source="unsplash",
                    source_url=_s(photo.get("photo_url")),
                    attribution=f"Photo by {_s(photo.get('photographer')) or 'Unknown'} on Unsplash",
                    alt_text=_s(photo.get("alt")),
                )
            )
    if not assets:
        if quota_exceeded:
            raise UnsplashError(413, "Storage quota exceeded. Free up space or upgrade your plan.")
        raise UnsplashError(502, "Could not import the selected photos.")
    return assets, failed
