"""Fixtures for the web API tests: an org owner signed in with the Django session."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace


@pytest.fixture
def workspace(db, organization):
    return Workspace.objects.create(name="Main", organization=organization)


@pytest.fixture
def second_workspace(db, organization):
    return Workspace.objects.create(name="Other", organization=organization)


@pytest.fixture
def member_client(db, org_owner, workspace, second_workspace):
    for ws in (workspace, second_workspace):
        WorkspaceMembership.objects.create(
            user=org_owner, workspace=ws, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
        )
    client = Client(enforce_csrf_checks=True)
    client.force_login(org_owner)
    return client
