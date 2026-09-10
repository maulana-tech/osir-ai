"""The signed-in person: profile, password, avatar, deletion, notifications, preferences."""

from __future__ import annotations

import uuid

from django.contrib.auth import logout, update_session_auth_hash
from django.utils import timezone
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.accounts import services as account_services
from apps.members.models import OrgMembership
from apps.notifications import preferences as prefs
from apps.notifications.models import EventType, Notification

router = Router(tags=["account"])


def _profile(user) -> dict:
    om = OrgMembership.objects.select_related("organization").filter(user=user).first()
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "display_name": user.display_name,
        "avatar_url": user.avatar.url if user.avatar else "",
        "totp_enabled": user.totp_enabled,
        "created_at": user.created_at.isoformat(),
        "organization": {"name": om.organization.name, "role": om.org_role} if om else None,
        "sole_owner_of": account_services.sole_owner_org_names(user),
    }


@router.get("/account", summary="Profile")
def account(request):
    return _profile(request.user)


class NameIn(Schema):
    name: str


@router.patch("/account", summary="Change display name")
def account_name(request, payload: NameIn):
    name = payload.name.strip()
    if not name:
        raise HttpError(400, "Name cannot be empty.")
    request.user.name = name
    request.user.save(update_fields=["name"])
    return _profile(request.user)


class PasswordIn(Schema):
    current_password: str
    password: str
    password_confirm: str


@router.post("/account/password", summary="Change password")
def account_password(request, payload: PasswordIn):
    try:
        account_services.change_password(
            request.user, payload.current_password, payload.password, payload.password_confirm
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    update_session_auth_hash(request, request.user)
    return {"changed": True}


@router.post("/account/avatar", summary="Upload or remove the profile photo")
def account_avatar(request, avatar: UploadedFile | None = File(None), remove: bool = Form(False)):  # noqa: B008
    user = request.user
    if remove:
        if user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
    elif avatar is not None:
        try:
            account_services.validate_avatar(avatar)
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
        if user.avatar:
            user.avatar.delete(save=False)
        user.avatar = avatar
    user.save()
    return {"avatar_url": user.avatar.url if user.avatar else ""}


@router.delete("/account", summary="Delete my account")
def account_delete(request):
    try:
        account_services.delete_account(request.user)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    logout(request)
    return {"deleted": True, "redirect": "/accounts/login/"}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "event_type": n.event_type,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat(),
    }


@router.get("/notifications", summary="Notification history")
def notifications(request, event_type: str = "", read_status: str = "", page: int = 1, per_page: int = 30):
    qs = Notification.objects.filter(user=request.user)
    if event_type:
        qs = qs.filter(event_type=event_type)
    if read_status == "read":
        qs = qs.filter(is_read=True)
    elif read_status == "unread":
        qs = qs.filter(is_read=False)
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    offset = (page - 1) * per_page
    total = qs.count()
    return {
        "notifications": [_notification(n) for n in qs[offset : offset + per_page]],
        "total": total,
        "page": page,
        "has_next": total > offset + per_page,
        "unread_count": Notification.objects.filter(user=request.user, is_read=False).count(),
        "event_types": [{"value": v, "label": label} for v, label in EventType.choices],
    }


@router.post("/notifications/{uuid:notification_id}/read", summary="Mark one as read")
def notification_read(request, notification_id: uuid.UUID):
    Notification.objects.filter(id=notification_id, user=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    return {"ok": True}


@router.post("/notifications/read-all", summary="Mark all as read")
def notifications_read_all(request):
    n = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
    return {"marked": n}


@router.get("/notification-preferences", summary="Event × channel matrix and quiet hours")
def preferences_get(request):
    return {"matrix": prefs.preference_matrix(request.user), "quiet_hours": prefs.quiet_hours_for(request.user)}


class Toggle(Schema):
    event_type: str
    channel: str
    enabled: bool


class QuietHoursIn(Schema):
    is_enabled: bool = False
    start_time: str = ""
    end_time: str = ""
    timezone: str = "UTC"
    digest_mode: bool = False


class PreferencesIn(Schema):
    toggles: list[Toggle]
    quiet_hours: QuietHoursIn


@router.put("/notification-preferences", summary="Save preferences")
def preferences_put(request, payload: PreferencesIn):
    try:
        prefs.save_preferences(
            request.user,
            {(t.event_type, t.channel): t.enabled for t in payload.toggles},
            payload.quiet_hours.model_dump(),
        )
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return preferences_get(request)
