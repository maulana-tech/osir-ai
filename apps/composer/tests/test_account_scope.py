"""``account_scope`` saves through the editor pipeline.

Regression coverage for the bug where opening a post from the calendar with
``?account=<id>`` rendered only that account, so saving (or the 30-second
autosave) deleted every sibling PlatformPost — including already-published
ones, cascading away their PublishLog history. Also pins the TikTok and
Pinterest panel semantics of ``normalize_platform_extra`` as reached via
``editor.save``.
"""

import pytest
from django.utils import timezone

from apps.composer import editor
from apps.composer.editor import AccountInput, EditorPayload
from apps.composer.models import PlatformPost, Post
from apps.publisher.models import PublishLog
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

PERMS = {"publish_directly": True, "approve_posts": True, "edit_others_posts": True}


def _account(workspace, platform, name):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform=platform,
        account_platform_id=f"{platform}-1",
        account_name=name,
        connection_status=SocialAccount.ConnectionStatus.CONNECTED,
    )


@pytest.fixture
def scene(db, organization, org_owner):
    ws = Workspace.objects.create(organization=organization, name="WS")
    youtube = _account(ws, "youtube", "YT Channel")
    tiktok = _account(ws, "tiktok", "janschmitz51")
    post = Post.objects.create(workspace=ws, author=org_owner, caption="hello")
    yt_pp = PlatformPost.objects.create(
        post=post,
        social_account=youtube,
        status=PlatformPost.Status.PUBLISHED,
        platform_post_id="yt-video-1",
        published_at=timezone.now(),
    )
    tt_pp = PlatformPost.objects.create(
        post=post,
        social_account=tiktok,
        status=PlatformPost.Status.FAILED,
        publish_error="TikTok API error 403: unaudited_client_can_only_post_to_private_accounts",
    )
    return ws, org_owner, post, youtube, tiktok, yt_pp, tt_pp


def _save(scene, **overrides):
    ws, user, post, _yt, tt, _yt_pp, _tt_pp = scene
    fields = {
        "action": "save_draft",
        "title": "Test post",
        "caption": "hello",
        "accounts": [AccountInput(id=str(tt.id))],
        "account_scope": str(tt.id),
    }
    fields.update(overrides)
    return editor.save(post, ws, user, PERMS, EditorPayload(**fields))


@pytest.mark.django_db
class TestScopedSave:
    def test_scoped_save_keeps_published_sibling(self, scene):
        yt_pp = scene[5]
        _save(scene)
        yt_pp.refresh_from_db()
        assert yt_pp.status == PlatformPost.Status.PUBLISHED

    def test_scoped_autosave_keeps_published_sibling_and_logs(self, scene):
        ws, user, post, _yt, tt, yt_pp, _tt_pp = scene
        log = PublishLog.objects.create(platform_post=yt_pp, attempt_number=1, status_code=200)
        editor.autosave(
            post,
            ws,
            user,
            EditorPayload(
                title="Test post", caption="hello", accounts=[AccountInput(id=str(tt.id))], account_scope=str(tt.id)
            ),
        )
        assert PlatformPost.objects.filter(id=yt_pp.id).exists()
        assert PublishLog.objects.filter(id=log.id).exists()

    def test_unscoped_deselect_never_deletes_published_row(self, scene):
        # Even the full (unscoped) composer must not hard-delete a published row.
        _save(scene, account_scope=None)
        assert PlatformPost.objects.filter(id=scene[5].id).exists()

    def test_unscoped_deselect_still_deletes_draft_row(self, scene):
        yt_pp = scene[5]
        yt_pp.status = PlatformPost.Status.DRAFT
        yt_pp.published_at = None
        yt_pp.save(update_fields=["status", "published_at"])
        _save(scene, account_scope=None)
        assert not PlatformPost.objects.filter(id=yt_pp.id).exists()

    def test_garbage_account_ids_ignored(self, scene):
        tt, yt_pp, tt_pp = scene[4], scene[5], scene[6]
        _save(scene, accounts=[AccountInput(id="not-a-uuid"), AccountInput(id=str(tt.id))])
        assert PlatformPost.objects.filter(id=tt_pp.id).exists()
        assert PlatformPost.objects.filter(id=yt_pp.id).exists()
        assert scene[2].platform_posts.count() == 2

    def test_scoped_publish_now_does_not_touch_draft_sibling(self, scene):
        yt_pp, tt_pp = scene[5], scene[6]
        yt_pp.status = PlatformPost.Status.DRAFT
        yt_pp.published_at = None
        yt_pp.save(update_fields=["status", "published_at"])
        _save(scene, action="publish_now")
        yt_pp.refresh_from_db()
        tt_pp.refresh_from_db()
        assert yt_pp.status == PlatformPost.Status.DRAFT and yt_pp.scheduled_at is None
        assert tt_pp.status == PlatformPost.Status.SCHEDULED and tt_pp.scheduled_at is not None

    def test_scoped_publish_now_does_not_reschedule_published_sibling(self, scene):
        yt_pp = scene[5]
        _save(scene, action="publish_now")
        yt_pp.refresh_from_db()
        assert yt_pp.status == PlatformPost.Status.PUBLISHED and yt_pp.scheduled_at is None


def _tiktok(scene, **extra):
    tt, tt_pp = scene[4], scene[6]
    _save(scene, accounts=[AccountInput(id=str(tt.id), extra=extra)])
    tt_pp.refresh_from_db()
    return tt_pp.platform_extra


@pytest.mark.django_db
class TestTikTokExtras:
    def test_settings_round_trip_into_platform_extra(self, scene):
        extra = _tiktok(scene, privacy_level="SELF_ONLY", allow_comment=True, brand_content=True, is_aigc=True)
        assert extra["privacy_level"] == "SELF_ONLY"
        assert extra["disable_comment"] is False
        # Duet/Stitch absent from the panel → both interactions disabled.
        assert extra["disable_duet"] is True and extra["disable_stitch"] is True
        assert extra["brand_content_toggle"] is True and extra["brand_organic_toggle"] is False
        assert extra["is_aigc"] is True

    def test_duet_and_stitch_toggle_independently(self, scene):
        extra = _tiktok(scene, privacy_level="SELF_ONLY", allow_duet=True)
        assert extra["disable_duet"] is False and extra["disable_stitch"] is True

    def test_invalid_privacy_level_left_unset(self, scene):
        assert "privacy_level" not in _tiktok(scene, privacy_level="BOGUS")

    def test_empty_privacy_value_preserves_saved_choice(self, scene):
        tt_pp = scene[6]
        tt_pp.platform_extra = {"privacy_level": "SELF_ONLY"}
        tt_pp.save(update_fields=["platform_extra"])
        assert _tiktok(scene, privacy_level="")["privacy_level"] == "SELF_ONLY"

    def test_extras_untouched_when_panel_absent(self, scene):
        tt_pp = scene[6]
        tt_pp.platform_extra = {"privacy_level": "SELF_ONLY"}
        tt_pp.save(update_fields=["platform_extra"])
        _save(scene)  # extra=None: the panel was not part of the submission
        tt_pp.refresh_from_db()
        assert tt_pp.platform_extra == {"privacy_level": "SELF_ONLY"}

    @pytest.mark.parametrize(
        ("cover", "expected"),
        [("12500", 12500), (12500, 12500), ("0", 0), ("", None), ("-5", None), ("²", None)],
    )
    def test_cover_timestamp(self, scene, cover, expected):
        extra = _tiktok(scene, privacy_level="PUBLIC_TO_EVERYONE", video_cover_timestamp_ms=cover)
        assert extra.get("video_cover_timestamp_ms") == expected


@pytest.fixture
def pinterest(scene):
    ws, _user, post = scene[0], scene[1], scene[2]
    account = _account(ws, "pinterest", "Pinterest")
    pp = PlatformPost.objects.create(post=post, social_account=account, status=PlatformPost.Status.DRAFT)
    return account, pp


@pytest.mark.django_db
class TestPinterestBoard:
    def _save(self, scene, pinterest, **extra):
        account, pp = pinterest
        _save(scene, accounts=[AccountInput(id=str(account.id), extra=extra)], account_scope=str(account.id))
        pp.refresh_from_db()
        return pp.platform_extra

    def test_selected_pinterest_account_requires_board(self, scene, pinterest):
        with pytest.raises(editor.EditorError) as exc:
            self._save(scene, pinterest)
        assert exc.value.field == "pinterest_board"

    def test_selected_pinterest_account_saves_board(self, scene, pinterest):
        assert self._save(scene, pinterest, board_id="board-123")["board_id"] == "board-123"

    def test_missing_board_field_preserves_existing_board(self, scene, pinterest):
        _account, pp = pinterest
        pp.platform_extra = {"board_id": "board-123"}
        pp.save(update_fields=["platform_extra"])
        assert self._save(scene, pinterest)["board_id"] == "board-123"
