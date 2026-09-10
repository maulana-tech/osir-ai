"""CSV planner import: parse, auto-map columns, validate rows, create posts."""

from __future__ import annotations

import csv
import io
import zoneinfo
from datetime import date as date_cls
from datetime import datetime
from datetime import time as time_cls

from apps.social_accounts.models import SocialAccount

from .models import ContentCategory, PlatformPost, Post

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

FIELD_MAP = {
    "date": ["date", "publish_date", "scheduled_date"],
    "time": ["time", "publish_time", "scheduled_time"],
    "platforms": ["platform", "platforms", "channel", "channels"],
    "caption": ["caption", "text", "content", "message", "body"],
    "media_url": ["media_url", "media", "image_url", "image", "video_url"],
    "category": ["category", "content_category", "type"],
    "tags": ["tags", "labels", "tag"],
    "first_comment": ["first_comment", "comment"],
}
FIELDS = list(FIELD_MAP)


def parse_upload(uploaded_file) -> tuple[list[str], list[list[str]]]:
    """``(headers, rows)``. Raises ValueError for oversized or empty files."""
    if uploaded_file.size and uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValueError("CSV file too large (max 5 MB).")
    rows = list(csv.reader(io.StringIO(uploaded_file.read().decode("utf-8-sig"))))
    if not rows:
        raise ValueError("CSV file is empty.")
    return rows[0], rows[1:]


def auto_mapping(headers) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, header in enumerate(headers):
        key = header.strip().lower().replace(" ", "_")
        for field, aliases in FIELD_MAP.items():
            if key in aliases and field not in mapping:
                mapping[field] = idx
                break
    return mapping


def clean_mapping(raw: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for field in FIELDS:
        v = raw.get(field, "")
        if v is None or v == "":
            continue
        try:
            out[field] = int(v)
        except (ValueError, TypeError):
            continue
    return out


def _cell(row, mapping, field) -> str:
    return row[mapping[field]].strip() if field in mapping and mapping[field] < len(row) else ""


def validate_rows(workspace, rows, mapping) -> dict:
    """Per-row problems plus the count of importable rows."""
    valid_platforms = {p[0].lower() for p in SocialAccount._meta.get_field("platform").choices or []}
    connected = set(
        SocialAccount.objects.for_workspace(workspace.id)
        .filter(connection_status=SocialAccount.ConnectionStatus.CONNECTED)
        .values_list("platform", flat=True)
    )
    errors = []
    valid = 0
    for n, row in enumerate(rows, start=2):
        problems = []
        if "date" in mapping:
            d = _cell(row, mapping, "date")
            if d:
                try:
                    date_cls.fromisoformat(d)
                except ValueError:
                    problems.append(f"Invalid date format '{d}' (expected YYYY-MM-DD)")
            else:
                problems.append("Date is empty")
        if "platforms" in mapping:
            for p in _cell(row, mapping, "platforms").split(","):
                p = p.strip().lower()
                if p and p not in valid_platforms:
                    problems.append(f"Unknown platform '{p}'")
                elif p and p not in connected:
                    problems.append(f"Platform '{p}' is not connected")
        if "caption" in mapping and not _cell(row, mapping, "caption"):
            problems.append("Caption is empty")
        if problems:
            errors.append({"row": n, "errors": problems})
        else:
            valid += 1
    return {"total_rows": len(rows), "valid_count": valid, "errors": errors[:50], "has_more_errors": len(errors) > 50}


def import_rows(workspace, user, rows, mapping) -> dict:
    """Create a post per row. Returns ``{created_count, error_count, total_rows}``."""
    created = errors = 0
    tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
    for row in rows:
        try:
            caption = _cell(row, mapping, "caption")
            if not caption:
                errors += 1
                continue
            post = Post(workspace=workspace, author=user, caption=caption)
            status = "draft"
            date_str = _cell(row, mapping, "date")
            if date_str:
                time_str = _cell(row, mapping, "time")
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                t = datetime.strptime(time_str, "%H:%M").time() if time_str else time_cls(9, 0)
                post.scheduled_at = datetime.combine(d, t).replace(tzinfo=tz)
                status = "scheduled"
            post.first_comment = _cell(row, mapping, "first_comment")
            tags_raw = _cell(row, mapping, "tags")
            if tags_raw:
                post.tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            cat_name = _cell(row, mapping, "category")
            if cat_name:
                post.category, _ = ContentCategory.objects.get_or_create(
                    workspace=workspace, name=cat_name, defaults={"color": "#3B82F6"}
                )
            post.save()
            for p in _cell(row, mapping, "platforms").split(","):
                p = p.strip().lower()
                if not p:
                    continue
                for acc in SocialAccount.objects.filter(
                    workspace=workspace, platform=p, connection_status=SocialAccount.ConnectionStatus.CONNECTED
                ):
                    PlatformPost.objects.get_or_create(
                        post=post, social_account=acc, defaults={"status": status, "scheduled_at": post.scheduled_at}
                    )
            created += 1
        except Exception:  # noqa: BLE001 - one bad row must not abort the import
            errors += 1
    return {"created_count": created, "error_count": errors, "total_rows": len(rows)}
