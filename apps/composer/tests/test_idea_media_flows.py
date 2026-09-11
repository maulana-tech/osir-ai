"""Idea media ordering / cover pointer (``ideas.sync_media``) and idea → draft conversion."""

import pytest

from apps.composer import ideas
from apps.composer.models import Idea, IdeaGroup
from apps.media_library.models import MediaAsset
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def ws(db, organization):
    return Workspace.objects.create(organization=organization, name="WS")


@pytest.fixture
def group(ws):
    return IdeaGroup.objects.create(workspace=ws, name="Backlog", position=0)


def _asset(ws, user, filename):
    return MediaAsset.objects.create(
        organization=ws.organization,
        workspace=ws,
        uploaded_by=user,
        file=f"media_library/tests/{filename}",
        filename=filename,
        media_type=MediaAsset.MediaType.IMAGE,
        mime_type="image/png",
        file_size=11,
        source="upload",
    )


def _idea(ws, user, group, **fields):
    fields.setdefault("title", "Idea")
    return Idea.objects.create(workspace=ws, author=user, group=group, status=Idea.Status.UNASSIGNED, **fields)


def _attached(idea):
    return [str(m) for m in idea.media_attachments.order_by("position").values_list("media_asset_id", flat=True)]


@pytest.mark.django_db
class TestSyncMedia:
    def test_attaches_ordered_media_and_sets_cover(self, ws, org_owner, group):
        one, two = _asset(ws, org_owner, "one.png"), _asset(ws, org_owner, "two.png")
        idea = _idea(ws, org_owner, group)
        ideas.sync_media(idea, ws, f"{two.id},{one.id}")
        idea.refresh_from_db()
        assert _attached(idea) == [str(two.id), str(one.id)] and idea.media_asset_id == two.id

    def test_appends_and_reorders(self, ws, org_owner, group):
        one, two, three = (_asset(ws, org_owner, f"{n}.png") for n in ("one", "two", "three"))
        idea = _idea(ws, org_owner, group, media_asset=one)
        idea.media_attachments.create(media_asset=one, position=0)
        ideas.sync_media(idea, ws, [two.id, one.id, three.id])
        idea.refresh_from_db()
        assert _attached(idea) == [str(two.id), str(one.id), str(three.id)] and idea.media_asset_id == two.id

    def test_removes_attachments_by_omission(self, ws, org_owner, group):
        one, two = _asset(ws, org_owner, "one.png"), _asset(ws, org_owner, "two.png")
        idea = _idea(ws, org_owner, group, media_asset=one)
        idea.media_attachments.create(media_asset=one, position=0)
        idea.media_attachments.create(media_asset=two, position=1)
        ideas.sync_media(idea, ws, str(two.id))
        idea.refresh_from_db()
        assert _attached(idea) == [str(two.id)] and idea.media_asset_id == two.id

    def test_ignores_garbage_and_foreign_assets(self, ws, org_owner, group, organization):
        other = Workspace.objects.create(organization=organization, name="Other")
        foreign = _asset(other, org_owner, "foreign.png")
        idea = _idea(ws, org_owner, group)
        ideas.sync_media(idea, ws, f"not-a-uuid,{foreign.id},")
        assert _attached(idea) == [] and idea.media_asset_id is None


@pytest.mark.django_db
class TestCreatePostFromIdea:
    def test_creates_mapped_draft_with_ordered_media_and_connected_platforms(self, ws, org_owner, group):
        one, two = _asset(ws, org_owner, "one.png"), _asset(ws, org_owner, "two.png")
        connected = [
            SocialAccount.objects.create(
                workspace=ws, platform=p, account_platform_id=p, account_name=p, connection_status="connected"
            )
            for p in ("instagram", "linkedin_company")
        ]
        SocialAccount.objects.create(
            workspace=ws,
            platform="facebook",
            account_platform_id="fb",
            account_name="fb",
            connection_status="disconnected",
        )
        idea = _idea(
            ws, org_owner, group, title="Convert", description="caption", tags=["alpha", "beta"], media_asset=one
        )
        idea.media_attachments.create(media_asset=two, position=0)
        idea.media_attachments.create(media_asset=one, position=1)

        post = ideas.create_post_from_idea(idea, ws, org_owner)
        idea.refresh_from_db()
        assert post.status == "draft" and idea.post_id == post.id
        assert (post.title, post.caption, post.tags) == ("Convert", "caption", ["alpha", "beta"])
        assert [
            str(m) for m in post.media_attachments.order_by("position").values_list("media_asset_id", flat=True)
        ] == [
            str(two.id),
            str(one.id),
        ]
        assert set(post.platform_posts.values_list("social_account_id", flat=True)) == {a.id for a in connected}

    def test_repeated_calls_create_new_posts_and_relink_idea(self, ws, org_owner, group):
        idea = _idea(ws, org_owner, group)
        first = ideas.create_post_from_idea(idea, ws, org_owner)
        second = ideas.create_post_from_idea(idea, ws, org_owner)
        idea.refresh_from_db()
        assert first.id != second.id and idea.post_id == second.id

    def test_falls_back_to_legacy_single_media_pointer(self, ws, org_owner, group):
        asset = _asset(ws, org_owner, "legacy.png")
        post = ideas.create_post_from_idea(_idea(ws, org_owner, group, media_asset=asset), ws, org_owner)
        assert [str(m) for m in post.media_attachments.values_list("media_asset_id", flat=True)] == [str(asset.id)]
