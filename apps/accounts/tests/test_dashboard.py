import pytest

from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace


@pytest.mark.django_db
def test_dashboard_redirects_into_the_console(client, org_owner, organization):
    client.force_login(org_owner)
    org_owner.last_workspace_id = None
    org_owner.save(update_fields=["last_workspace_id"])
    assert client.get("/").headers["Location"] == "/org/workspaces"
    ws = Workspace.objects.create(name="WS", organization=organization)
    WorkspaceMembership.objects.create(user=org_owner, workspace=ws, workspace_role="owner")
    org_owner.last_workspace_id = ws.id
    org_owner.save(update_fields=["last_workspace_id"])
    assert client.get("/").headers["Location"] == f"/w/{ws.id}/calendar"
    ws.is_archived = True
    ws.save(update_fields=["is_archived"])
    assert client.get("/").headers["Location"] == "/org/workspaces"
