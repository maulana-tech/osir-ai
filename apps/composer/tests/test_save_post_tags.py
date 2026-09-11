"""Tag handling in the editor pipeline.

``autosave`` is lenient (truncates like the old form POST did); ``save`` uses
the strict JSON contract (``normalize_tags`` → ``EditorError``). XSS payloads
are stored verbatim — render-time escaping is the security boundary.
"""

import pytest

from apps.common.validators import MAX_TAG_LENGTH, MAX_TAGS, MAX_YT_TAGS_TOTAL_CHARS
from apps.composer import editor
from apps.composer.editor import AccountInput, EditorPayload
from apps.composer.models import PlatformPost
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.fixture
def ws(db, organization):
    return Workspace.objects.create(organization=organization, name="WS")


def _autosave(ws, user, tags):
    return editor.autosave(None, ws, user, EditorPayload(title="t", caption="body", tags=tags))


def _save(ws, user, tags, accounts=()):
    return editor.save(None, ws, user, {}, EditorPayload(title="t", caption="body", tags=tags, accounts=list(accounts)))


@pytest.mark.django_db
class TestPostTags:
    def test_autosave_truncates_30_tags_to_max(self, ws, org_owner):
        post = _autosave(ws, org_owner, [f"tag{i}" for i in range(30)])
        assert len(post.tags) == MAX_TAGS
        assert post.tags[0] == "tag0" and post.tags[-1] == f"tag{MAX_TAGS - 1}"

    def test_autosave_truncates_oversized_tag(self, ws, org_owner):
        assert _autosave(ws, org_owner, ["x" * (MAX_TAG_LENGTH + 50)]).tags == ["x" * MAX_TAG_LENGTH]

    def test_save_rejects_too_many_tags(self, ws, org_owner):
        with pytest.raises(editor.EditorError) as exc:
            _save(ws, org_owner, [f"tag{i}" for i in range(MAX_TAGS + 1)])
        assert exc.value.field == "tags"

    def test_xss_payload_persists_verbatim(self, ws, org_owner):
        payload = "<script>alert(1)</script>"
        assert _save(ws, org_owner, [payload]).tags == [payload]

    def test_empty_tags_stores_empty_list(self, ws, org_owner):
        assert _save(ws, org_owner, []).tags == []

    def test_yt_tags_truncated_to_total_chars_cap(self, ws, org_owner):
        yt = SocialAccount.objects.create(
            workspace=ws,
            platform="youtube",
            account_platform_id="yt-1",
            account_name="YT",
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        )
        # 25 tags × 30 chars + 24 delimiters = 774 > 500. Must truncate.
        post = _save(ws, org_owner, [], accounts=[AccountInput(id=str(yt.id), extra={"tags": ["y" * 30] * 25})])
        stored = PlatformPost.objects.get(post=post, social_account=yt).platform_extra["tags"]
        assert 0 < sum(len(t) for t in stored) + max(0, len(stored) - 1) <= MAX_YT_TAGS_TOTAL_CHARS
