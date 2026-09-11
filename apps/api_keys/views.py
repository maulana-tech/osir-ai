"""Issuance helpers shared with the web API (``apps/webapi/routers/admin.py``).

The API-keys page itself is rendered by the Next.js console; ``urls.py`` only
keeps the ``api_keys:list`` name alive as a redirect.
"""

from __future__ import annotations

from apps.members.models import PERMISSION_KEYS, WorkspaceMembership

# Permission keys defined in the registry but intentionally hidden from
# API-key issuance until the feature they gate ships. Stored API keys may
# still carry these strings; they just don't appear in the picker.
_HIDDEN_FROM_ISSUANCE: set[str] = set()


def _grantable_permissions(user, workspace, *, include_hidden: bool = False) -> list[tuple[str, str]]:
    """Return ``[(perm_key, label), ...]`` of permissions the user can grant in ``workspace``.

    Mirrors what ``services.issue_api_key`` enforces server-side: an issuer can
    only grant a permission they themselves hold via their workspace
    membership. ``include_hidden`` keeps issuance-hidden permissions in the
    list (the edit flow needs the full held set so nothing is silently
    stripped on save). Labels are the titlecased slug.
    """
    try:
        membership = WorkspaceMembership.objects.select_related("custom_role").get(user=user, workspace=workspace)
    except WorkspaceMembership.DoesNotExist:
        return []
    held = {k for k, v in membership.effective_permissions.items() if v}
    return [
        (k, k.replace("_", " ").capitalize())
        for k in PERMISSION_KEYS
        if k in held and (include_hidden or k not in _HIDDEN_FROM_ISSUANCE)
    ]
