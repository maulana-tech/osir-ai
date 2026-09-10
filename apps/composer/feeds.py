"""RSS / Atom feed subscriptions for the Create page: fetch, parse, cache, validate."""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
from dateutil import parser as date_parser
from django.core.cache import cache
from django.utils import timezone
from django.utils.html import strip_tags

from apps.common.validators import is_safe_url, safe_xml_fromstring

from .models import Feed

FEED_EVENTS_PAGE_SIZE = 15
FEED_EVENTS_CACHE_TTL_SECONDS = 10 * 60
_IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
_HEADERS = {
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.1",
    "User-Agent": "Osir AI RSS Reader/1.0",
}


def cache_key(workspace_id):
    return f"composer:feed-events:{workspace_id}"


def normalize_selected_feed_id(selected_feed_id, feeds):
    return selected_feed_id if selected_feed_id in {str(f.id) for f in feeds} else "all"


def coerce_positive_int(value, default=0):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _local_name(tag):
    if not tag:
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1].lower()
    if ":" in tag:
        return tag.split(":", 1)[-1].lower()
    return tag.lower()


def _first_child(element, *names):
    wanted = {n.lower() for n in names}
    for child in element:
        if _local_name(child.tag) in wanted:
            return child
    return None


def _first_child_text(element, *names):
    child = _first_child(element, *names)
    return (child.text or "").strip() if child is not None else ""


def _atom_link(entry):
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "").strip().lower()
        if href and rel in ("", "alternate"):
            return href
    for child in entry:
        if _local_name(child.tag) == "link" and (child.attrib.get("href") or "").strip():
            return child.attrib["href"].strip()
    return ""


def _image_url(entry, summary_raw):
    for node in entry.iter():
        name = _local_name(node.tag)
        if name not in {"thumbnail", "content", "enclosure"}:
            continue
        url = (node.attrib.get("url") or node.attrib.get("href") or node.attrib.get("src") or "").strip()
        media_type = (node.attrib.get("type") or "").lower()
        medium = (node.attrib.get("medium") or "").lower()
        if url and (name == "thumbnail" or medium == "image" or media_type.startswith("image/") or not media_type):
            return url
    if summary_raw:
        m = _IMG_SRC_RE.search(summary_raw)
        if m:
            return m.group(1)
    return ""


def _clean_summary(raw):
    return re.sub(r"\s+", " ", strip_tags(raw)).strip() if raw else ""


def _published_at(raw):
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError, OverflowError):
        parsed = date_parser.parse(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def parse_feed_document(xml_content):
    """RSS / Atom / RDF → ``{title, website_url, entries, entry_kind}`` or None (size-bounded, DTD-free)."""
    if isinstance(xml_content, str):
        xml_content = xml_content.encode("utf-8", errors="replace")
    root = safe_xml_fromstring(xml_content)
    if root is None:
        return None
    name = _local_name(root.tag)
    if name == "rss":
        channel = _first_child(root, "channel")
        if channel is None:
            return None
        return {
            "title": _first_child_text(channel, "title"),
            "website_url": _first_child_text(channel, "link"),
            "entries": [c for c in channel if _local_name(c.tag) == "item"],
            "entry_kind": "rss",
        }
    if name == "feed":
        return {
            "title": _first_child_text(root, "title"),
            "website_url": _atom_link(root),
            "entries": [c for c in root if _local_name(c.tag) == "entry"],
            "entry_kind": "atom",
        }
    if name == "rdf":
        channel = _first_child(root, "channel")
        return {
            "title": _first_child_text(channel, "title") if channel is not None else "",
            "website_url": _first_child_text(channel, "link") if channel is not None else "",
            "entries": [c for c in root if _local_name(c.tag) == "item"],
            "entry_kind": "rss",
        }
    return None


def _event(feed, parsed, entry):
    if parsed["entry_kind"] == "atom":
        raw_title = _first_child_text(entry, "title")
        raw_link = _atom_link(entry)
        raw_summary = _first_child_text(entry, "summary") or _first_child_text(entry, "content")
        raw_published = (
            _first_child_text(entry, "published")
            or _first_child_text(entry, "updated")
            or _first_child_text(entry, "issued")
        )
    else:
        raw_title = _first_child_text(entry, "title")
        raw_link = _first_child_text(entry, "link")
        raw_summary = (
            _first_child_text(entry, "description")
            or _first_child_text(entry, "summary")
            or _first_child_text(entry, "content")
        )
        raw_published = (
            _first_child_text(entry, "pubDate")
            or _first_child_text(entry, "published")
            or _first_child_text(entry, "updated")
            or _first_child_text(entry, "date")
        )
    title = raw_title or parsed["title"] or feed.name or "Untitled"
    link = raw_link or parsed["website_url"] or feed.website_url
    return {
        "event_id": (link or f"{feed.id}:{title}:{raw_published}").strip(),
        "feed_id": str(feed.id),
        "feed_name": feed.name,
        "feed_favicon_url": feed.favicon_url,
        "feed_website_url": feed.website_url or parsed["website_url"],
        "title": title,
        "link": link,
        "summary": _clean_summary(raw_summary),
        "image_url": _image_url(entry, raw_summary),
        "published_at": _published_at(raw_published),
    }


def safe_fetch(url, headers=None, *, timeout=8.0, max_redirects=5):
    """GET with manual redirects, re-checking every hop against SSRF. ``(response, final_url)`` or ``(None, None)``."""
    headers = headers or _HEADERS
    if not is_safe_url(url):
        return None, None
    current = url
    try:
        response = httpx.get(current, headers=headers, timeout=timeout, follow_redirects=False)
    except httpx.RequestError:
        return None, None
    for _ in range(max_redirects):
        if response.status_code not in (301, 302, 303, 307, 308):
            return response, current
        location = response.headers.get("Location")
        if not location:
            return None, None
        nxt = urljoin(current, location)
        if not is_safe_url(nxt):
            return None, None
        try:
            response = httpx.get(nxt, headers=headers, timeout=timeout, follow_redirects=False)
        except httpx.RequestError:
            return None, None
        current = nxt
    return None, None


def fetch_events(feeds):
    """Recent entries across ``feeds``, deduplicated, newest first."""
    if not feeds:
        return []
    events = []
    for feed in feeds:
        response, _ = safe_fetch(feed.url)
        if response is None or response.status_code >= 400:
            continue
        parsed = parse_feed_document(response.content)
        if not parsed:
            continue
        events.extend(_event(feed, parsed, e) for e in parsed["entries"][:50])
    seen: set = set()
    out = []
    for ev in events:
        key = (ev["feed_id"], ev["event_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    out.sort(key=lambda ev: ev["published_at"] or datetime(1970, 1, 1, tzinfo=UTC), reverse=True)
    return out


def cached_events(workspace, feeds, force_refresh=False):
    key = cache_key(workspace.id)
    signature = tuple((str(f.id), f.url, f.name, f.website_url) for f in feeds)
    cached = cache.get(key)
    if cached and not force_refresh and cached.get("signature") == signature:
        return cached.get("events", []), cached.get("fetched_at")
    events = fetch_events(feeds)
    fetched_at = timezone.now()
    cache.set(key, {"signature": signature, "events": events, "fetched_at": fetched_at}, FEED_EVENTS_CACHE_TTL_SECONDS)
    return events, fetched_at


def events_context(workspace, selected_feed_id="all", offset=0):
    feeds = list(Feed.objects.for_workspace(workspace.id))
    selected_feed_id = normalize_selected_feed_id(selected_feed_id, feeds)
    events, last_refreshed_at = cached_events(workspace, feeds)
    filtered = events if selected_feed_id == "all" else [e for e in events if e["feed_id"] == selected_feed_id]
    next_offset = offset + FEED_EVENTS_PAGE_SIZE
    return {
        "feeds": feeds,
        "selected_feed_id": selected_feed_id,
        "selected_feed": next((f for f in feeds if str(f.id) == selected_feed_id), None),
        "events": filtered[offset:next_offset],
        "next_offset": next_offset,
        "has_more": len(filtered) > next_offset,
        "last_refreshed_at": last_refreshed_at,
        "total_event_count": len(filtered),
    }


def validate_rss_url(rss_url):
    """``(ok, error, {title, website_url})`` for a candidate feed URL."""
    response, _ = safe_fetch(rss_url, {**_HEADERS, "User-Agent": "Osir AI RSS Validator/1.0"})
    if response is None:
        return False, "Could not reach this URL. Please check the link and try again.", {}
    if response.status_code >= 400:
        return False, "This URL could not be loaded as a feed.", {}
    parsed = parse_feed_document(response.content)
    if not parsed:
        return False, "This URL is reachable, but it does not appear to be a valid RSS/Atom feed.", {}
    return True, "", {"title": parsed.get("title", "").strip(), "website_url": parsed.get("website_url", "").strip()}


def add_feed(workspace, user, rss_url, *, name="", website_url="", validate=True):
    """Subscribe the workspace to ``rss_url``. Raises ValueError with a person-facing message."""
    from django.core.exceptions import ValidationError
    from django.core.validators import URLValidator

    rss_url = (rss_url or "").strip()
    if not rss_url:
        raise ValueError("Feed URL is required.")
    try:
        URLValidator()(rss_url)
    except ValidationError as exc:
        raise ValueError("Invalid URL.") from exc
    meta: dict = {}
    if validate:
        ok, error, meta = validate_rss_url(rss_url)
        if not ok:
            raise ValueError(error)
    if Feed.objects.for_workspace(workspace.id).filter(url=rss_url).exists():
        raise ValueError("Already subscribed to this feed.")
    feed = Feed.objects.create(
        workspace=workspace,
        name=name or meta.get("title") or rss_url,
        url=rss_url,
        website_url=website_url or meta.get("website_url", ""),
        added_by=user,
    )
    cache.delete(cache_key(workspace.id))
    return feed


def remove_feed(feed):
    workspace_id = feed.workspace_id
    feed.delete()
    cache.delete(cache_key(workspace_id))


def explore(workspace, category):
    from .curated_feeds import get_feed_categories, get_feeds_for_category

    subscribed = set(Feed.objects.for_workspace(workspace.id).values_list("url", flat=True))
    curated = get_feeds_for_category(category)
    for f in curated:
        f["subscribed"] = f["rss"] in subscribed
    return {"categories": get_feed_categories(), "active_category": category, "curated_feeds": curated}
