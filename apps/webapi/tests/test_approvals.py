"""Approval actions through the web API: request changes, bulk, comment edit scope, media re-review."""

from __future__ import annotations

import json
import secrets

import pytest
from django.core.files.base import ContentFile

from apps.approvals.models import ApprovalAction, PostComment
from apps.composer.models import PlatformPost, Post, PostMedia
from apps.media_library.models import MediaAsset
from apps.social_accounts.models import SocialAccount


def _send(client, method, path, data=None):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    kwargs = {"HTTP_X_CSRFTOKEN": token}
    if data is not None:
        kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(client, method)(path, **kwargs)


@pytest.fixture
def account(workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id="li-1",
        account_name="LI",
        connection_status="connected",
    )


def _post(workspace, account, author, status, **fields):
    post = Post.objects.create(workspace=workspace, author=author, caption="Original caption", **fields)
    PlatformPost.objects.create(post=post, social_account=account, status=status)
    return post


def _status(post):
    return post.platform_posts.get().status


@pytest.mark.django_db
class TestActions:
    def test_request_changes_requires_comment(self, member_client, workspace, account, org_owner):
        post = _post(workspace, account, org_owner, "pending_review")
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{workspace.id}/approvals/{post.id}/request-changes",
            {"comment": ""},
        )
        assert r.status_code == 400
        assert _status(post) == "pending_review"

    def test_request_changes_with_comment(self, member_client, workspace, account, org_owner):
        post = _post(workspace, account, org_owner, "pending_review")
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{workspace.id}/approvals/{post.id}/request-changes",
            {"comment": "Tighten the hook"},
        )
        assert r.status_code == 200
        assert r.json()["platform_statuses"] == ["changes_requested"]
        assert ApprovalAction.objects.filter(post=post, action="changes_requested").exists()

    def test_bulk_reject_requires_comment(self, member_client, workspace, account, org_owner):
        post = _post(workspace, account, org_owner, "pending_review")
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{workspace.id}/approvals/bulk",
            {"action": "reject", "post_ids": [str(post.id)]},
        )
        assert r.status_code == 400
        assert _status(post) == "pending_review"

    def test_bulk_approve(self, member_client, workspace, account, org_owner):
        p1 = _post(workspace, account, org_owner, "pending_review")
        p2 = _post(workspace, account, org_owner, "pending_review")
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{workspace.id}/approvals/bulk",
            {"action": "approve", "post_ids": [str(p1.id), str(p2.id)]},
        )
        assert r.status_code == 200
        assert r.json()["updated"] == 2
        assert _status(p1) == "approved" and _status(p2) == "approved"


@pytest.mark.django_db
class TestCommentEditScope:
    """V9: editing a comment must be scoped to the workspace in the URL."""

    @pytest.fixture
    def comment(self, second_workspace, org_owner):
        post = Post.objects.create(workspace=second_workspace, author=org_owner, caption="b")
        return PostComment.objects.create(
            post=post, author=org_owner, body="hi", visibility=PostComment.Visibility.INTERNAL
        )

    def test_cross_workspace_edit_returns_404(self, member_client, workspace, comment):
        # The comment lives in the second workspace, but the request goes through the first one's URL.
        r = _send(
            member_client,
            "put",
            f"/api/web/workspaces/{workspace.id}/posts/{comment.post_id}/comments/{comment.id}",
            {"body": "rewritten"},
        )
        assert r.status_code == 404
        comment.refresh_from_db()
        assert comment.body == "hi"

    def test_same_workspace_edit_succeeds(self, member_client, second_workspace, comment):
        r = _send(
            member_client,
            "put",
            f"/api/web/workspaces/{second_workspace.id}/posts/{comment.post_id}/comments/{comment.id}",
            {"body": "rewritten"},
        )
        assert r.status_code == 200
        assert r.json()["body"] == "rewritten"
        comment.refresh_from_db()
        assert comment.body == "rewritten"


# The retired HTMX attach/remove-media views called ``editor.revert_approved_to_review``
# themselves; ``editor.save`` only re-reviews when ``base_content_snapshot`` (text fields)
# changes, so a media-only edit through the web API still leaves the post approved.
@pytest.mark.xfail(strict=True, reason="editor.save does not yet treat a media change as a content change")
@pytest.mark.django_db
class TestMediaEditReReview:
    """Changing media on an approved post sends it back for re-approval (Option A)."""

    def _asset(self, workspace):
        return MediaAsset.objects.create(
            organization=workspace.organization,
            workspace=workspace,
            file=ContentFile(b"x", name="pic.png"),
            filename="pic.png",
            media_type=MediaAsset.MediaType.IMAGE,
        )

    def _save(self, client, workspace, post, account, media_asset_ids):
        return _send(
            client,
            "post",
            f"/api/web/workspaces/{workspace.id}/composer/posts/{post.id}",
            {
                "action": "save_draft",
                "caption": post.caption,
                "accounts": [{"id": str(account.id)}],
                "media_asset_ids": media_asset_ids,
            },
        )

    def test_attaching_media_reverts_approved(self, member_client, workspace, account, org_owner):
        post = _post(workspace, account, org_owner, "approved")
        r = self._save(member_client, workspace, post, account, [str(self._asset(workspace).id)])
        assert r.status_code == 200
        assert _status(post) == "pending_review"

    def test_removing_media_reverts_approved(self, member_client, workspace, account, org_owner):
        post = _post(workspace, account, org_owner, "approved")
        PostMedia.objects.create(post=post, media_asset=self._asset(workspace), position=0)
        r = self._save(member_client, workspace, post, account, [])
        assert r.status_code == 200
        assert _status(post) == "pending_review"
