"""Account (profile) operations shared by the HTMX view and the web API."""

from __future__ import annotations

from PIL import Image

AVATAR_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MIN_SIDE = 180


def validate_avatar(upload) -> None:
    if upload.content_type not in AVATAR_TYPES:
        raise ValueError("Photo must be a JPEG, PNG, WebP, or GIF image.")
    if upload.size > AVATAR_MAX_BYTES:
        raise ValueError("Photo must be under 2 MB.")
    try:
        width, height = Image.open(upload).size
    except Exception as exc:
        raise ValueError("Could not read image file.") from exc
    finally:
        upload.seek(0)
    if width < AVATAR_MIN_SIDE or height < AVATAR_MIN_SIDE:
        raise ValueError("Photo must be at least 180×180 pixels.")


def change_password(user, current: str, new: str, confirm: str) -> None:
    if not current:
        raise ValueError("Current password is required.")
    if not user.check_password(current):
        raise ValueError("Current password is incorrect.")
    if not new:
        raise ValueError("New password cannot be empty.")
    if len(new) < 8:
        raise ValueError("New password must be at least 8 characters.")
    if new != confirm:
        raise ValueError("New passwords do not match.")
    user.set_password(new)
    user.save()


def sole_owner_org_names(user) -> list[str]:
    """Organizations that would be left without an owner if ``user`` disappeared."""
    from apps.members.models import OrgMembership

    names = []
    for m in OrgMembership.objects.filter(user=user, org_role=OrgMembership.OrgRole.OWNER).select_related(
        "organization"
    ):
        others = (
            OrgMembership.objects.filter(organization=m.organization, org_role=OrgMembership.OrgRole.OWNER)
            .exclude(user=user)
            .exists()
        )
        if not others:
            names.append(m.organization.name)
    return names


def delete_account(user) -> None:
    names = sole_owner_org_names(user)
    if names:
        raise ValueError(
            f"You are the sole owner of: {', '.join(names)}. "
            "Transfer ownership or delete the organization before deleting your account."
        )
    user.delete()
