"""The proposal store on the database: only the caller's, only while waiting, only once."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.actions.adapters import DjangoActionStore
from core.actions.types import Draft, Field, Proposal
from core.errors import ActionUnavailable

pytestmark = pytest.mark.django_db(transaction=True)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def proposal(**changes) -> Proposal:
    values = dict(
        id=uuid4(),
        action_id="leave_request",
        title="Leave request",
        icon="calendar",
        conversation_id=uuid4(),
        caller_id="E100",
        draft=Draft("Annual leave", (Field("Days", "5"),), {"type": "annual"}, ("9 left",)),
        expires_at=NOW + timedelta(minutes=10),
    )
    return Proposal(**{**values, **changes})


async def test_a_proposal_is_kept_as_its_card_shows_it() -> None:
    store, made = DjangoActionStore(), proposal()
    await store.create(made)
    [found] = await store.for_conversation(made.conversation_id, "E100")
    assert (found.draft, found.status, found.title) == (made.draft, "proposed", "Leave request")
    assert await store.for_conversation(made.conversation_id, "E999") == []


async def test_it_is_claimed_once_even_by_two_clicks_at_once() -> None:
    store, made = DjangoActionStore(), proposal()
    await store.create(made)
    outcomes = await asyncio.gather(
        store.claim(made.id, "E100", NOW), store.claim(made.id, "E100", NOW), return_exceptions=True
    )
    claimed = [o for o in outcomes if isinstance(o, Proposal)]
    refused = [o for o in outcomes if isinstance(o, ActionUnavailable)]
    assert len(claimed) == 1 and claimed[0].status == "sending"
    assert [r.reason for r in refused] == ["sending"]


async def test_another_persons_or_a_late_proposal_cannot_be_claimed() -> None:
    store, made = DjangoActionStore(), proposal()
    await store.create(made)
    with pytest.raises(ActionUnavailable) as other:
        await store.claim(made.id, "E999", NOW)
    assert other.value.reason == "not_found"
    with pytest.raises(ActionUnavailable) as late:
        await store.claim(made.id, "E100", NOW + timedelta(minutes=11))
    assert late.value.reason == "expired"
    [kept] = await store.for_conversation(made.conversation_id, "E100")
    assert kept.status == "expired"  # the expiry is kept, not rolled back with the refusal


async def test_finishing_and_cancelling() -> None:
    store, sent, dropped = DjangoActionStore(), proposal(), proposal()
    for made in (sent, dropped):
        await store.create(made)
    await store.claim(sent.id, "E100", NOW)
    done = await store.finish(sent.id, "sent", "LV-1", "Waiting for manager")
    assert (done.status, done.reference, done.outcome) == ("sent", "LV-1", "Waiting for manager")
    assert (await store.cancel(dropped.id, "E100", NOW)).status == "cancelled"
    with pytest.raises(ActionUnavailable):
        await store.cancel(dropped.id, "E100", NOW)
