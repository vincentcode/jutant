import pytest
from asgiref.sync import sync_to_async

from apps.conversation import selectors
from apps.conversation.adapters import DjangoConversationStore, to_citations
from core.types import Caller, Citation, Message, ToolCall

pytestmark = pytest.mark.django_db(transaction=True)
TELLER = Caller("S0042", "teller", "staff", {})


async def test_round_trip_through_the_store() -> None:
    store = DjangoConversationStore()
    conversation_id = await store.create(TELLER)
    call = ToolCall("1", "documents.search", {"query": "kyc"})
    citation = Citation("document", "KYC Policy", "4.2")

    await store.append(conversation_id, Message("user", "kyc?"))
    await store.append(conversation_id, Message("assistant", "", tool_calls=(call,)))
    await store.append(conversation_id, Message("assistant", "Answer."), "policy_qa", (citation,))

    history = await store.recent_messages(conversation_id, 6)
    assert [m.content for m in history] == ["kyc?", "", "Answer."]
    assert history[1].tool_calls == (call,)
    rows = await sync_to_async(selectors.messages)(conversation_id=conversation_id)
    assert rows[2].feature_id == "policy_qa"
    assert to_citations(rows[2]) == (citation,)
    conversation = await sync_to_async(selectors.get_conversation)(
        conversation_id=conversation_id, staff_id="S0042"
    )
    assert conversation is not None
