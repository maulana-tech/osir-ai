"""The composer through the web API."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.composer.models import ContentCategory, Idea, IdeaGroup, PlatformPost, Post, PostTemplate, Tag
from apps.social_accounts.models import SocialAccount


def _send(client, method, path, data=None, **extra):
    token = secrets.token_hex(16)
    client.cookies["csrftoken"] = token
    kwargs = {"HTTP_X_CSRFTOKEN": token, **extra}
    if data is not None:
        kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(client, method)(path, **kwargs)


@pytest.fixture
def accounts(workspace):
    yt = SocialAccount.objects.create(
        workspace=workspace,
        platform="youtube",
        account_platform_id="yt",
        account_name="YT",
        connection_status="connected",
    )
    tt = SocialAccount.objects.create(
        workspace=workspace,
        platform="tiktok",
        account_platform_id="tt",
        account_name="TT",
        connection_status="connected",
    )
    return yt, tt


@pytest.mark.django_db
class TestComposer:
    def test_context_lists_accounts_and_perms(self, member_client, workspace, accounts):
        body = member_client.get(f"/api/web/workspaces/{workspace.id}/composer/context?template=161").json()
        assert {a["platform"] for a in body["accounts"]} == {"youtube", "tiktok"}
        yt = next(a for a in body["accounts"] if a["platform"] == "youtube")
        assert yt["needs_title"] is True and yt["char_limit"] > 0
        assert body["perms"]["publish_directly"] is True
        assert body["post"] is None and "caption" in body["initial"]["template"]

    def test_save_draft_then_schedule_with_extras(self, member_client, workspace, accounts):
        yt, tt = accounts
        base = f"/api/web/workspaces/{workspace.id}/composer/posts"
        r = _send(
            member_client,
            "post",
            base,
            {
                "action": "save_draft",
                "title": "Hello",
                "caption": "world",
                "tags": ["Launch", "launch"],
                "accounts": [
                    {
                        "id": str(yt.id),
                        "extra": {"privacy_status": "unlisted", "tags": ["a", "b"], "made_for_kids": False},
                    },
                    {
                        "id": str(tt.id),
                        "caption": "tiktok caption",
                        "extra": {
                            "privacy_level": "SELF_ONLY",
                            "allow_comment": True,
                            "video_cover_timestamp_ms": 1200,
                        },
                    },
                ],
                "scheduled_date": "2030-01-01",
                "scheduled_time": "09:00",
            },
        )
        assert r.status_code == 200, r.content
        post_id = r.json()["id"]
        post = Post.objects.get(id=post_id)
        assert post.tags == ["Launch", "launch"] and post.proposed_publish_at is not None
        yt_pp = post.platform_posts.get(social_account=yt)
        assert yt_pp.platform_extra["privacy_status"] == "unlisted" and yt_pp.platform_extra["tags"] == ["a", "b"]
        tt_pp = post.platform_posts.get(social_account=tt)
        assert tt_pp.platform_specific_caption == "tiktok caption"
        assert tt_pp.platform_extra["privacy_level"] == "SELF_ONLY"
        assert tt_pp.platform_extra["disable_duet"] is True and tt_pp.platform_extra["video_cover_timestamp_ms"] == 1200
        assert post.versions.count() == 1

        detail = member_client.get(f"/api/web/workspaces/{workspace.id}/composer/context?post_id={post_id}").json()
        assert detail["post"]["schedule_is_proposed"] is True and detail["post"]["scheduled_date"] == "2030-01-01"

        when = timezone.now() + timedelta(days=1)
        r = _send(
            member_client,
            "post",
            f"{base}/{post_id}",
            {
                "action": "schedule",
                "title": "Hello",
                "caption": "world",
                "accounts": [{"id": str(yt.id)}, {"id": str(tt.id), "extra": None}],
                "scheduled_date": when.strftime("%Y-%m-%d"),
                "scheduled_time": when.strftime("%H:%M"),
            },
        )
        assert r.status_code == 200, r.content
        assert set(r.json()["platform_statuses"].values()) == {"scheduled"}
        post.refresh_from_db()
        assert post.proposed_publish_at is None and post.scheduled_at is not None
        # A panel that was absent (extra=None) keeps its stored choice.
        assert post.platform_posts.get(social_account=tt).platform_extra["privacy_level"] == "SELF_ONLY"

    def test_schedule_in_past_and_publish_permission(self, member_client, workspace, accounts):
        yt, _ = accounts
        base = f"/api/web/workspaces/{workspace.id}/composer/posts"
        r = _send(
            member_client,
            "post",
            base,
            {
                "action": "schedule",
                "caption": "x",
                "accounts": [{"id": str(yt.id)}],
                "scheduled_date": "2000-01-01",
                "scheduled_time": "09:00",
            },
        )
        assert r.status_code == 400 and "future" in r.json()["detail"]

    def test_delete_clone_template_and_transition(self, member_client, workspace, accounts):
        yt, tt = accounts
        base = f"/api/web/workspaces/{workspace.id}/composer/posts"
        post_id = _send(
            member_client, "post", base, {"caption": "c", "accounts": [{"id": str(yt.id)}, {"id": str(tt.id)}]}
        ).json()["id"]
        r = _send(member_client, "post", f"{base}/{post_id}/save-as-template", {"name": "T1"})
        assert r.status_code == 200 and PostTemplate.objects.filter(name="T1").exists()
        clone_id = _send(member_client, "post", f"{base}/{post_id}/clone").json()["id"]
        assert Post.objects.get(id=clone_id).caption == "c"
        pp = PlatformPost.objects.get(post_id=post_id, social_account=tt)
        r = _send(
            member_client, "post", f"{base}/{post_id}/platform-posts/{pp.id}/transition", {"target_status": "scheduled"}
        )
        assert r.status_code == 200 and r.json()["status"] == "scheduled"
        assert _send(member_client, "delete", f"{base}/{post_id}?account={tt.id}").status_code == 200
        assert PlatformPost.objects.filter(post_id=post_id).count() == 1
        assert _send(member_client, "delete", f"{base}/{post_id}").status_code == 200
        assert not Post.objects.filter(id=post_id).exists()

    def test_categories_tags_templates(self, member_client, workspace):
        ws = workspace.id
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{ws}/composer/categories",
            {"name": "Promo", "color": "#123456"},
        )
        assert r.status_code == 200
        cid = r.json()["id"]
        assert (
            _send(
                member_client,
                "patch",
                f"/api/web/workspaces/{ws}/composer/categories/{cid}",
                {"name": "Promo2", "color": "zzz"},
            ).status_code
            == 400
        )
        assert (
            _send(
                member_client,
                "patch",
                f"/api/web/workspaces/{ws}/composer/categories/{cid}",
                {"name": "Promo2", "color": "#000000"},
            ).json()["name"]
            == "Promo2"
        )
        assert _send(member_client, "delete", f"/api/web/workspaces/{ws}/composer/categories/{cid}").status_code == 200
        assert not ContentCategory.objects.filter(id=cid).exists()
        assert (
            _send(member_client, "post", f"/api/web/workspaces/{ws}/composer/tags", {"name": " hero "}).json()["name"]
            == "hero"
        )
        assert Tag.objects.filter(workspace=workspace, name="hero").exists()
        body = member_client.get(f"/api/web/workspaces/{ws}/composer/templates").json()
        assert len(body["builtin"]) > 10 and body["saved"] == []

    def test_ideas_board(self, member_client, workspace, accounts):
        ws = workspace.id
        board = member_client.get(f"/api/web/workspaces/{ws}/composer/ideas").json()
        assert [c["name"] for c in board["columns"]] == ["Unassigned", "To Do", "In Progress", "Done"]
        todo = board["columns"][1]["id"]
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{ws}/composer/ideas",
            {"title": "Idea", "tags": ["x"], "group_id": todo},
        )
        assert r.status_code == 200
        idea_id = r.json()["id"]
        assert r.json()["group_id"] == todo
        r = _send(member_client, "post", f"/api/web/workspaces/{ws}/composer/idea-groups", {"name": "Later"})
        gid = r.json()["id"]
        assert (
            _send(
                member_client,
                "post",
                f"/api/web/workspaces/{ws}/composer/ideas/{idea_id}/move",
                {"group_id": gid, "position": 0},
            ).status_code
            == 200
        )
        assert Idea.objects.get(id=idea_id).group_id.hex == IdeaGroup.objects.get(id=gid).id.hex
        assert _send(member_client, "delete", f"/api/web/workspaces/{ws}/composer/idea-groups/{gid}").status_code == 400
        r = _send(member_client, "post", f"/api/web/workspaces/{ws}/composer/ideas/{idea_id}/create-post")
        post = Post.objects.get(id=r.json()["post_id"])
        assert post.title == "Idea" and post.platform_posts.count() == 2
        assert _send(member_client, "delete", f"/api/web/workspaces/{ws}/composer/ideas/{idea_id}").status_code == 200

    def test_csv_flow(self, member_client, workspace, accounts):
        ws = workspace.id
        token = secrets.token_hex(16)
        member_client.cookies["csrftoken"] = token
        import io

        f = io.BytesIO(b"date,platform,caption\n2030-01-01,youtube,Hello\n,youtube,\n")
        f.name = "posts.csv"
        r = member_client.post(f"/api/web/workspaces/{ws}/composer/csv/upload", {"csv_file": f}, HTTP_X_CSRFTOKEN=token)
        assert r.status_code == 200, r.content
        assert r.json()["auto_mapping"] == {"date": 0, "platforms": 1, "caption": 2}
        r = _send(
            member_client,
            "post",
            f"/api/web/workspaces/{ws}/composer/csv/validate",
            {"mapping": r.json()["auto_mapping"]},
        )
        assert r.json()["valid_count"] == 1 and len(r.json()["errors"]) == 1
        r = _send(member_client, "post", f"/api/web/workspaces/{ws}/composer/csv/confirm")
        assert r.json()["created_count"] == 1
        assert Post.objects.filter(workspace=workspace, caption="Hello", platform_posts__status="scheduled").exists()
