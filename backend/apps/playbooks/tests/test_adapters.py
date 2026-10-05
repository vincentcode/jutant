from uuid import uuid4

import pytest
from asgiref.sync import sync_to_async

from apps.playbooks import services
from apps.playbooks.adapters import DjangoPlaybookStore
from apps.playbooks.tests.factories import BLOCKED_CARD
from core.types import PlaybookRunState

pytestmark = pytest.mark.django_db(transaction=True)


async def test_store_reads_playbooks_and_keeps_run_state() -> None:
    await sync_to_async(services.upsert_playbook)(definition=BLOCKED_CARD)
    store = DjangoPlaybookStore()
    conversation_id = uuid4()

    assert await store.get("blocked_card") == BLOCKED_CARD
    assert [p.id for p in await store.list()] == ["blocked_card"]
    with pytest.raises(KeyError):
        await store.get("missing")

    state = PlaybookRunState("blocked_card", 2, {1: "confirm"}, "active", "troubleshooting")
    await store.save_run(conversation_id, state)
    assert await store.get_run(conversation_id) == state

    await store.save_run(conversation_id, PlaybookRunState("blocked_card", 2, {}, "abandoned"))
    assert await store.get_run(conversation_id) is None
