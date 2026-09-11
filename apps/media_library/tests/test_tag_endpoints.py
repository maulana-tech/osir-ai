"""HTTP-level tests for the media library tag-update endpoint.

Covers the ``PUT /api/web/workspaces/<id>/media/<asset_id>/tags`` contract:
validation, overflow rejection, dedup, cross-workspace isolation, and that a
malicious payload is stored verbatim (escaping is the renderer's job).
"""

import json

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.common.validators import MAX_TAG_LENGTH, MAX_TAGS
from apps.media_library.models import MediaAsset
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace


class AssetTagEndpointTests(TestCase):
    """PUT /api/web/workspaces/<id>/media/<asset_id>/tags"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="testpass123",
            tos_accepted_at=timezone.now(),
        )
        self.org = Organization.objects.create(name="Test Org")
        self.workspace = Workspace.objects.create(organization=self.org, name="Test Workspace")
        OrgMembership.objects.create(
            user=self.user,
            organization=self.org,
            org_role=OrgMembership.OrgRole.OWNER,
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
        )
        self.asset = MediaAsset.objects.create(
            organization=self.org,
            workspace=self.workspace,
            uploaded_by=self.user,
            file="media_library/tests/asset.png",
            filename="asset.png",
            media_type=MediaAsset.MediaType.IMAGE,
            mime_type="image/png",
            file_size=128,
            source="upload",
        )
        self.client.force_login(self.user)
        self.url = f"/api/web/workspaces/{self.workspace.id}/media/{self.asset.id}/tags"

    def _put(self, tags):
        return self.client.put(self.url, data=json.dumps({"tags": tags}), content_type="application/json")

    def test_happy_path_persists_tags(self):
        response = self._put(["alpha", "beta", "gamma"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tags": ["alpha", "beta", "gamma"]})
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.tags, ["alpha", "beta", "gamma"])

    def test_dedupes_tags(self):
        response = self._put(["alpha", "alpha", "beta", "alpha"])
        self.assertEqual(response.status_code, 200)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.tags, ["alpha", "beta"])

    def test_strips_whitespace(self):
        self._put(["  alpha  ", "beta"])
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.tags, ["alpha", "beta"])

    def test_rejects_over_max_tags(self):
        response = self._put([f"t{i}" for i in range(MAX_TAGS + 1)])
        self.assertEqual(response.status_code, 400)
        self.assertIn("too many tags", response.json()["detail"])

    def test_rejects_oversized_tag(self):
        response = self._put(["x" * (MAX_TAG_LENGTH + 1)])
        self.assertEqual(response.status_code, 400)
        self.assertIn("too long", response.json()["detail"])

    def test_rejects_non_list_body(self):
        # Schema validation: ``tags`` must be a list of strings.
        response = self._put({"foo": "bar"})
        self.assertEqual(response.status_code, 422)

    def test_rejects_non_string_element(self):
        response = self._put(["alpha", 123, "beta"])
        self.assertEqual(response.status_code, 422)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.tags, [])

    def test_unauthenticated_request_is_401(self):
        self.client.logout()
        self.assertEqual(self._put(["alpha"]).status_code, 401)

    def test_cross_workspace_user_gets_403(self):
        """User not a member of this workspace must not reach the route at all.

        The RBAC middleware rejects with PermissionDenied (403) before the
        router runs, so the asset's existence is not leaked.
        """
        other_user = User.objects.create_user(
            email="outsider@example.com",
            password="testpass123",
            tos_accepted_at=timezone.now(),
        )
        other_org = Organization.objects.create(name="Other Org")
        other_ws = Workspace.objects.create(organization=other_org, name="Other WS")
        OrgMembership.objects.create(user=other_user, organization=other_org, org_role=OrgMembership.OrgRole.OWNER)
        WorkspaceMembership.objects.create(
            user=other_user, workspace=other_ws, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
        )
        self.client.force_login(other_user)
        response = self._put(["alpha"])
        self.assertEqual(response.status_code, 403)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.tags, [])

    def test_xss_payload_persists_verbatim(self):
        """The string is stored verbatim; escaping happens when the console renders it."""
        payload = "<script>alert(1)</script>"
        response = self._put([payload])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tags": [payload]})
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.tags, [payload])
