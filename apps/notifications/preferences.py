"""Per-user notification preferences: the event × channel matrix and quiet hours."""

from __future__ import annotations

from datetime import time as dt_time
from zoneinfo import available_timezones

from .engine import DEFAULT_CHANNELS
from .models import Channel, EventType, NotificationPreference, QuietHours


def preference_matrix(user) -> list[dict]:
    """One row per event type, each with the enabled state of every channel."""
    stored = {(p.event_type, p.channel): p.is_enabled for p in NotificationPreference.objects.filter(user=user)}
    rows = []
    for event_value, event_label in EventType.choices:
        rows.append(
            {
                "event_type": event_value,
                "label": event_label,
                "channels": [
                    {
                        "channel": ch_value,
                        "label": ch_label,
                        "enabled": stored.get(
                            (event_value, ch_value), DEFAULT_CHANNELS.get(event_value, {}).get(ch_value, False)
                        ),
                    }
                    for ch_value, ch_label in Channel.choices
                ],
            }
        )
    return rows


def quiet_hours_for(user) -> dict:
    qh, _ = QuietHours.objects.get_or_create(user=user)
    return {
        "is_enabled": qh.is_enabled,
        "start_time": qh.start_time.strftime("%H:%M") if qh.start_time else "",
        "end_time": qh.end_time.strftime("%H:%M") if qh.end_time else "",
        "timezone": qh.timezone,
        "digest_mode": qh.digest_mode,
    }


def _parse_hhmm(value: str) -> dt_time | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        hours, minutes = value.split(":")
        return dt_time(int(hours), int(minutes))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid time: {value}") from exc


def save_preferences(user, toggles: dict[tuple[str, str], bool], quiet: dict) -> None:
    """``toggles`` maps ``(event_type, channel)`` to enabled; unknown keys are ignored."""
    for event_value, _ in EventType.choices:
        for ch_value, _ in Channel.choices:
            NotificationPreference.objects.update_or_create(
                user=user,
                event_type=event_value,
                channel=ch_value,
                defaults={"is_enabled": bool(toggles.get((event_value, ch_value), False))},
            )
    qh, _ = QuietHours.objects.get_or_create(user=user)
    qh.is_enabled = bool(quiet.get("is_enabled", False))
    qh.start_time = _parse_hhmm(quiet.get("start_time", ""))
    qh.end_time = _parse_hhmm(quiet.get("end_time", ""))
    tz = (quiet.get("timezone") or "UTC").strip()
    if tz not in available_timezones():
        raise ValueError("Invalid timezone.")
    qh.timezone = tz
    qh.digest_mode = bool(quiet.get("digest_mode", False))
    qh.save()
