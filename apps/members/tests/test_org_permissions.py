"""Tests for the org-level permission model and ``@require_org_permission``."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.members.decorators import require_org_permission
from apps.members.models import (
    BUILTIN_ORG_PERMISSIONS,
    ORG_PERMISSION_KEYS,
    OrgMembership,
    WorkspaceMembership,
    has_org_permission,
)
from apps.organizations.models import Organization


def _make_user(email):
    user = User.objects.create_user(email=email, password="testpass123", tos_accepted_at=timezone.now())
    # The accounts post_save signal auto-provisions a default Org; start clean.
    auto_org_ids = list(OrgMembership.objects.filter(user=user).values_list("organization_id", flat=True))
    WorkspaceMembership.objects.filter(user=user).delete()
    OrgMembership.objects.filter(user=user).delete()
    Organization.objects.filter(id__in=auto_org_ids).delete()
    return user


def _member(email, org, role):
    return OrgMembership.objects.create(user=_make_user(email), organization=org, org_role=role)


class OrgPermissionTableTests(TestCase):
    def test_owner_and_admin_have_every_key_member_has_none(self):
        keys = {k for k, _ in ORG_PERMISSION_KEYS}
        self.assertEqual(BUILTIN_ORG_PERMISSIONS[OrgMembership.OrgRole.OWNER], keys)
        self.assertEqual(BUILTIN_ORG_PERMISSIONS[OrgMembership.OrgRole.ADMIN], keys)
        self.assertEqual(BUILTIN_ORG_PERMISSIONS[OrgMembership.OrgRole.MEMBER], set())

    def test_has_org_permission(self):
        org = Organization.objects.create(name="Acme")
        self.assertFalse(has_org_permission(None, "manage_api_keys"))
        self.assertTrue(
            has_org_permission(_member("o@example.com", org, OrgMembership.OrgRole.OWNER), "manage_api_keys")
        )
        self.assertFalse(
            has_org_permission(_member("m@example.com", org, OrgMembership.OrgRole.MEMBER), "manage_api_keys")
        )


class RequireOrgPermissionDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.org = Organization.objects.create(name="Acme")

        @require_org_permission("manage_api_keys")
        def keys_view(request, *args, **kwargs):
            return HttpResponse(f"ok org={request.org.id} mem={request.org_membership.org_role}")

        self.keys_view = keys_view

    def _request_as(self, user, *, org_id):
        req = self.factory.get(f"/orgs/{org_id}/api-keys/")
        req.user = user
        return req

    def test_anonymous_redirected_to_login(self):
        from django.contrib.auth.models import AnonymousUser

        req = self._request_as(AnonymousUser(), org_id=self.org.id)
        self.assertEqual(self.keys_view(req, org_id=self.org.id).status_code, 302)

    def test_owner_and_admin_admitted_with_request_org_attached(self):
        for email, role in (
            ("o@example.com", OrgMembership.OrgRole.OWNER),
            ("a@example.com", OrgMembership.OrgRole.ADMIN),
        ):
            m = _member(email, self.org, role)
            resp = self.keys_view(self._request_as(m.user, org_id=self.org.id), org_id=self.org.id)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(str(self.org.id).encode(), resp.content)
            self.assertIn(f"mem={role}".encode(), resp.content)

    def test_member_denied(self):
        m = _member("m@example.com", self.org, OrgMembership.OrgRole.MEMBER)
        with self.assertRaises(PermissionDenied):
            self.keys_view(self._request_as(m.user, org_id=self.org.id), org_id=self.org.id)

    def test_cross_org_membership_and_non_member_rejected(self):
        other = Organization.objects.create(name="Other Co")
        m = _member("alice@example.com", other, OrgMembership.OrgRole.OWNER)
        with self.assertRaises(PermissionDenied):
            self.keys_view(self._request_as(m.user, org_id=self.org.id), org_id=self.org.id)
        nobody = _make_user("nobody@example.com")
        with self.assertRaises(PermissionDenied):
            self.keys_view(self._request_as(nobody, org_id=self.org.id), org_id=self.org.id)

    def test_missing_org_id_in_url_raises(self):
        m = _member("o@example.com", self.org, OrgMembership.OrgRole.OWNER)
        req = self.factory.get("/no-org-id/")
        req.user = m.user
        with self.assertRaises(PermissionDenied):
            self.keys_view(req)
