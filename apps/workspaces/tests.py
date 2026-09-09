import pytest
from django.test import Client

from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace


@pytest.mark.django_db
def test_approvals_settings_saves_agent_autonomy(org_owner, organization):
    workspace = Workspace.objects.create(name="WS", organization=organization)
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client = Client()
    client.force_login(org_owner)
    url = f"/workspaces/{workspace.id}/settings/approvals/"

    r = client.post(url, {"approval_workflow_mode": "optional", "agent_autonomy": "autopilot"})
    assert r.status_code == 302
    workspace.refresh_from_db()
    assert workspace.agent_autonomy == Workspace.AgentAutonomy.AUTOPILOT
    assert workspace.approval_workflow_mode == Workspace.ApprovalWorkflowMode.OPTIONAL

    r = client.post(url, {"approval_workflow_mode": "optional", "agent_autonomy": "bogus"})
    assert r.status_code == 302
    workspace.refresh_from_db()
    assert workspace.agent_autonomy == Workspace.AgentAutonomy.AUTOPILOT
