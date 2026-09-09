"""Per-test cache isolation for the MCP transport surface.

See the docstring of ``apps/api/tests/conftest.py`` — the MCP transport
uses the same ``ApiKeyAuth`` and therefore the same failed-auth bucket,
so the same isolation applies.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_failed_auth_throttle():
    from django.core.cache import cache

    cache.delete("agent_api:auth_fail:127.0.0.1")
    yield
    cache.delete("agent_api:auth_fail:127.0.0.1")


# ---------------------------------------------------------------------------
# Shared scaffold for the MCP tool tests: an owner-issued key scoped to
# ``social_account`` (and NOT ``second_account``, for allowlist tests).
# ---------------------------------------------------------------------------

from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.api_keys import services  # noqa: E402
from apps.members.models import PERMISSION_KEYS, OrgMembership, WorkspaceMembership  # noqa: E402


class _SecureClient(Client):
    """Forces ``secure=True`` so the bearer HTTPS guard doesn't 401 every call."""

    def generic(self, method, path, *args, **kwargs):
        kwargs["secure"] = True
        return super().generic(method, path, *args, **kwargs)


@pytest.fixture
def user(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        email="mcp-owner@example.com",
        password="testpass123",
        name="MCP Owner",
        tos_accepted_at=timezone.now(),
    )


@pytest.fixture
def organization(db):
    from apps.organizations.models import Organization

    return Organization.objects.create(name="MCP Org")


@pytest.fixture
def workspace(db, organization):
    from apps.workspaces.models import Workspace

    return Workspace.objects.create(name="MCP Workspace", organization=organization)


@pytest.fixture
def owner_memberships(db, user, organization, workspace):
    OrgMembership.objects.create(user=user, organization=organization, org_role=OrgMembership.OrgRole.OWNER)
    return WorkspaceMembership.objects.create(
        user=user,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
    )


@pytest.fixture
def social_account(db, workspace):
    from apps.social_accounts.models import SocialAccount

    return SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id="li-mcp",
        account_name="LinkedIn MCP",
        connection_status="connected",
    )


@pytest.fixture
def second_account(db, workspace):
    """A SocialAccount in the same workspace that the MCP key is NOT
    scoped to — used for confused-deputy regression tests.
    """
    from apps.social_accounts.models import SocialAccount

    return SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id="li-mcp-second",
        account_name="LinkedIn MCP 2",
        connection_status="connected",
    )


@pytest.fixture
def issued_key(db, user, owner_memberships, workspace, social_account):
    return services.issue_api_key(
        workspace=workspace,
        social_accounts=[social_account],
        issued_by=user,
        name="mcp",
        permissions=list(PERMISSION_KEYS),
    )


@pytest.fixture
def client_with_token(issued_key):
    return _SecureClient(HTTP_AUTHORIZATION=f"Bearer {issued_key.plaintext_token}")
