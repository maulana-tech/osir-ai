"""Proposed publishing datetime — service + editor behaviour.

A draft can carry an optional ``proposed_publish_at`` suggestion, entered via
the Schedule panel. Saving a draft captures it; scheduling clears it; and a
post that is already scheduled must never have the panel reinterpreted as a
proposal.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.calendar.models import PostingSlot, Queue
from apps.composer import editor
from apps.composer.editor import AccountInput, EditorPayload
from apps.composer.models import PlatformPost, Post
from apps.composer.services import create_post
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

BERLIN = ZoneInfo("Europe/Berlin")
# 2027-09-01 is CEST (UTC+2), so 09:00 local == 07:00 UTC — an unambiguous instant.
PROPOSED_LOCAL = datetime(2027, 9, 1, 9, 0, tzinfo=BERLIN)
PERMS = {"publish_directly": True}


@pytest.fixture
def ws(db, organization):
    return Workspace.objects.create(organization=organization, name="WS", timezone="Europe/Berlin")


@pytest.fixture
def sa(ws):
    return SocialAccount.objects.create(
        workspace=ws,
        platform="linkedin_personal",
        account_platform_id="li-1",
        account_name="Acct",
        connection_status=SocialAccount.ConnectionStatus.CONNECTED,
    )


@pytest.fixture
def draft(ws, sa, org_owner):
    return create_post(
        workspace=ws,
        social_account=sa,
        caption="body",
        status="draft",
        proposed_publish_at=PROPOSED_LOCAL,
        author=org_owner,
    )


def _save(post, ws, user, sa, **fields):
    fields.setdefault("caption", "body")
    fields.setdefault("accounts", [AccountInput(id=str(sa.id))])
    return editor.save(post, ws, user, PERMS, EditorPayload(**fields))


@pytest.mark.django_db
class TestCreatePost:
    """create_post stores the optional proposal independent of status."""

    def test_create_post_stores_proposed(self, ws, sa):
        post = create_post(
            workspace=ws, social_account=sa, caption="hi", status="draft", proposed_publish_at=PROPOSED_LOCAL
        )
        # Re-fetch so this proves persistence, not just the in-memory attribute.
        assert Post.objects.get(pk=post.pk).proposed_publish_at == PROPOSED_LOCAL

    def test_create_post_defaults_to_none(self, ws, sa):
        assert create_post(workspace=ws, social_account=sa, caption="hi", status="draft").proposed_publish_at is None

    def test_scheduling_clears_proposed(self, ws, sa):
        # create_post(status='scheduled') routes through sync_post_scheduled_at,
        # which drops any proposal centrally — the two never coexist.
        post = create_post(
            workspace=ws,
            social_account=sa,
            caption="hi",
            status="scheduled",
            scheduled_at=timezone.now() + timedelta(days=10),
            proposed_publish_at=PROPOSED_LOCAL,
        )
        post = Post.objects.get(pk=post.pk)
        assert post.scheduled_at is not None and post.proposed_publish_at is None


@pytest.mark.django_db
class TestEditorProposed:
    def test_save_draft_captures_proposed_in_workspace_tz(self, ws, sa, org_owner):
        post = _save(None, ws, org_owner, sa, scheduled_date=date(2027, 9, 1), scheduled_time=time(9, 0))
        post.refresh_from_db()
        assert post.proposed_publish_at == PROPOSED_LOCAL
        # A proposal is NOT a schedule — the publisher column stays empty.
        assert post.scheduled_at is None

    def test_save_draft_blank_clears_proposed(self, ws, sa, org_owner, draft):
        _save(draft, ws, org_owner, sa)
        draft.refresh_from_db()
        assert draft.proposed_publish_at is None

    def test_schedule_clears_proposed_and_sets_scheduled(self, ws, sa, org_owner, draft):
        _save(draft, ws, org_owner, sa, action="schedule", scheduled_date=date(2027, 9, 1), scheduled_time=time(9, 0))
        draft.refresh_from_db()
        assert draft.proposed_publish_at is None and draft.scheduled_at is not None
        assert draft.platform_posts.filter(status="scheduled").exists()

    def test_save_draft_on_scheduled_post_leaves_schedule_untouched(self, ws, sa, org_owner):
        when = timezone.now().astimezone(BERLIN).replace(microsecond=0) + timedelta(days=30)
        post = Post.objects.create(workspace=ws, author=org_owner, caption="x", scheduled_at=when)
        PlatformPost.objects.create(post=post, social_account=sa, status="scheduled", scheduled_at=when)
        _save(post, ws, org_owner, sa, caption="x", scheduled_date=date(2027, 9, 1), scheduled_time=time(9, 0))
        post.refresh_from_db()
        # Already-scheduled → the panel is the live schedule, not a proposal.
        assert post.proposed_publish_at is None and post.scheduled_at == when
        assert post.platform_posts.filter(status="scheduled").exists()

    def test_submit_for_approval_with_blank_panel_preserves_proposed(self, ws, sa, org_owner, draft):
        # A proposal set via the API must survive being routed through approval
        # even when the submit carries no schedule-panel values.
        _save(draft, ws, org_owner, sa, action="submit_for_approval")
        draft.refresh_from_db()
        assert draft.proposed_publish_at == PROPOSED_LOCAL
        assert draft.platform_posts.filter(status="pending_review").exists()

    def test_chip_transition_to_scheduled_clears_proposed(self, draft):
        # The per-account chip bypasses save(); it must still drop the proposal
        # when it commits a child to publishing.
        pp = draft.platform_posts.get()
        editor.transition_child(pp, "scheduled", PERMS)
        draft.refresh_from_db()
        assert draft.proposed_publish_at is None
        # The clear must not disturb the scheduling aggregate the publisher reads.
        assert draft.scheduled_at is None
        pp.refresh_from_db()
        assert pp.status == "scheduled"

    def test_publisher_fallback_still_picks_up_scheduled_post(self, ws, sa, org_owner):
        # A scheduled child with NULL scheduled_at must stay "due" via the
        # Post.scheduled_at Coalesce fallback; proposal handling must never
        # disturb that aggregate, else such a post would silently never publish.
        from apps.publisher.engine import PublishEngine

        past = timezone.now() - timedelta(minutes=5)
        post = Post.objects.create(workspace=ws, author=org_owner, caption="x", scheduled_at=past)
        pp = PlatformPost.objects.create(post=post, social_account=sa, status="scheduled", scheduled_at=None)
        assert pp.id in {d.id for d in PublishEngine()._get_due_platform_posts()}


@pytest.fixture
def daily_queue(ws, sa):
    """A 09:00 slot every day + a queue, so the soonest open slot is within ~1 day."""
    for day in range(7):
        PostingSlot.objects.create(social_account=sa, day_of_week=day, time=time(9, 0))
    return Queue.objects.create(workspace=ws, name="Q", social_account=sa)


@pytest.mark.django_db
class TestQueueIgnoresPrefilledDate:
    """Editing a draft prefills the Schedule panel from its proposed/scheduled
    time. The queue actions must NOT treat that date as a slot floor (which
    bumped posts to next week); both use the soonest open slot."""

    @pytest.mark.parametrize("action", ["add_to_queue", "add_to_queue_priority"])
    def test_existing_draft(self, ws, sa, org_owner, daily_queue, action):
        floor = timezone.now() + timedelta(days=14)
        local = floor.astimezone(BERLIN)
        post = create_post(
            workspace=ws, social_account=sa, caption="body", status="draft", proposed_publish_at=floor, author=org_owner
        )
        _save(post, ws, org_owner, sa, action=action, scheduled_date=local.date(), scheduled_time=local.time())
        pp = post.platform_posts.get(social_account=sa)
        assert pp.scheduled_at is not None
        # Soonest 09:00 slot is within ~1 day — NOT floored to +14d.
        assert pp.scheduled_at < timezone.now() + timedelta(days=3)

    def test_new_post_uses_global_next_slot(self, ws, sa, org_owner, daily_queue):
        # The calendar "+" CTA opens a NEW post with scheduled_date prefilled to
        # the clicked day; queueing uses the global next slot regardless.
        local = (timezone.now() + timedelta(days=10)).astimezone(BERLIN)
        post = _save(
            None, ws, org_owner, sa, action="add_to_queue", scheduled_date=local.date(), scheduled_time=local.time()
        )
        pp = post.platform_posts.get(social_account=sa)
        assert pp.scheduled_at is not None and pp.scheduled_at < timezone.now() + timedelta(days=3)
