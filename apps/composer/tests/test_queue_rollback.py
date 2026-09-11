"""Add-to-Queue must be atomic across queues: a full queue rolls back partials."""

from datetime import time

import pytest

from apps.calendar.models import PostingSlot, Queue, QueueEntry
from apps.composer import editor
from apps.composer.editor import AccountInput, EditorPayload
from apps.composer.models import PlatformPost, Post
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


@pytest.mark.django_db
def test_full_queue_rolls_back_the_other_queue_writes(organization, org_owner):
    ws = Workspace.objects.create(organization=organization, name="RB WS")
    # Account A has posting slots; account B has none, so its queue is always full.
    acct_a = SocialAccount.objects.create(
        workspace=ws, platform="linkedin_personal", account_platform_id="li-a", account_name="A"
    )
    acct_b = SocialAccount.objects.create(
        workspace=ws, platform="bluesky", account_platform_id="bs-b", account_name="B"
    )
    for day in range(7):
        PostingSlot.objects.create(social_account=acct_a, day_of_week=day, time=time(9, 0))
    Queue.objects.create(workspace=ws, name="QA", social_account=acct_a)
    Queue.objects.create(workspace=ws, name="QB", social_account=acct_b)
    post = Post.objects.create(workspace=ws, author=org_owner, caption="multi")
    pp_a = PlatformPost.objects.create(post=post, social_account=acct_a, status=PlatformPost.Status.DRAFT)
    pp_b = PlatformPost.objects.create(post=post, social_account=acct_b, status=PlatformPost.Status.DRAFT)

    payload = EditorPayload(
        action="add_to_queue",
        caption="multi",
        accounts=[AccountInput(id=str(acct_a.id)), AccountInput(id=str(acct_b.id))],
    )
    with pytest.raises(editor.EditorError) as exc:
        editor.save(post, ws, org_owner, {}, payload)
    assert exc.value.message == editor.QUEUE_FULL_MSG

    # No partial state: no queue entries, both children still draft + unscheduled.
    assert QueueEntry.objects.filter(post=post).count() == 0
    for pp in (pp_a, pp_b):
        pp.refresh_from_db()
        assert pp.scheduled_at is None and pp.status == PlatformPost.Status.DRAFT
