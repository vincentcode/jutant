from uuid import uuid4

import pytest

from core.errors import ModelUnavailable, PolicyDenied
from core.events import Completed, Failed, FeatureSelected, TextDelta, ToolFinished, ToolStarted
from core.orchestrator.orchestrator import NO_SOURCE_MESSAGE
from core.types import Caller, Citation, Message, ModelReply, ToolCall
from providers.llm.fake import FakeModel
from tests.builders import (
    collect_events,
    doc_result,
    final_answer,
    make_rig,
    record_result,
    spec,
    teller,
)


def search(query: str, call_id: str = "1") -> ModelReply:
    return ModelReply(
        text=None, tool_calls=(ToolCall(call_id, "documents.search", {"query": query}),)
    )


async def test_policy_question_calls_search_and_cites() -> None:
    model = FakeModel(
        replies=[search("KYC joint account"), ModelReply("Both holders must provide ID.")]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    answer = await final_answer(
        rig.orchestrator.ask(teller(), uuid4(), "KYC for joint accounts?", "policy_qa")
    )

    assert answer.text == "Both holders must provide ID."
    assert answer.citations == (Citation("document", "KYC Policy", "4.2"),)
    assert model.calls[0].tools == [spec("documents.search")]  # only the feature's tools
    assert rig.tools.calls[0].caller.role == "teller"


async def test_event_order_for_a_tool_turn() -> None:
    model = FakeModel(replies=[search("kyc"), ModelReply("Answer.")])
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    assert [type(e) for e in events] == [
        FeatureSelected,
        ToolStarted,
        ToolFinished,
        TextDelta,
        Completed,
    ]


async def test_uncited_document_answer_is_replaced() -> None:
    # Answers from memory twice: once before being told to use its tools, once after.
    model = FakeModel(replies=[ModelReply("From memory: two IDs."), ModelReply("Still two IDs.")])
    rig = await make_rig(model)

    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert texts == [NO_SOURCE_MESSAGE]  # the uncited text never reaches the client
    assert events[-1].answer.text == NO_SOURCE_MESSAGE


async def test_a_first_reply_without_a_tool_call_is_nudged_to_use_tools() -> None:
    model = FakeModel(
        replies=[
            ModelReply("E51 means a bad account number (Manual 4.2.1)."),  # invented
            search("E51"),
            ModelReply("E51: beneficiary account closed."),
        ]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("Error codes", "E51")})

    answer = await final_answer(rig.orchestrator.ask(teller(), uuid4(), "E51?", "policy_qa"))

    assert answer.text == "E51: beneficiary account closed."
    assert answer.citations == (Citation("document", "Error codes", "E51"),)
    nudged = model.calls[1].messages
    assert nudged[-1].role == "user"
    assert nudged[-1].content.startswith("E51?") and "documents.search" in nudged[-1].content
    assert not any("Manual 4.2.1" in m.content for m in nudged)  # the invented answer is dropped


async def test_the_nudge_is_given_only_once() -> None:
    model = FakeModel(replies=[ModelReply(""), ModelReply("")])
    rig = await make_rig(model)
    await collect_events(rig.orchestrator.ask(teller(), uuid4(), "E51?", "policy_qa"))
    assert len(model.calls) == 2


async def test_invalid_arguments_are_returned_to_the_model_once() -> None:
    bad = ModelReply(text=None, tool_calls=(ToolCall("1", "documents.search", {"q": "kyc"}),))
    model = FakeModel(replies=[bad, search("kyc", "2"), ModelReply("Answer.")])
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    answer = await final_answer(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    assert answer.text == "Answer."
    retry_messages = model.calls[1].messages
    assert retry_messages[-1].role == "tool"
    assert "invalid_arguments" in retry_messages[-1].content


async def test_second_tool_failure_ends_the_turn() -> None:
    bad = ModelReply(text=None, tool_calls=(ToolCall("1", "documents.search", {"q": "kyc"}),))
    model = FakeModel(replies=[bad, bad, ModelReply("never used")])
    rig = await make_rig(model)

    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    assert events[-1] == Failed("tool_failed")
    assert "answer_returned" in rig.audit.names()


async def test_tool_outside_the_feature_is_refused_and_reported_to_the_model() -> None:
    wrong = ModelReply(
        text=None, tool_calls=(ToolCall("1", "transactions.get_status", {"query": "x"}),)
    )
    model = FakeModel(replies=[wrong, search("kyc", "2"), ModelReply("Answer.")])
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    answer = await final_answer(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    assert [c.call.name for c in rig.tools.calls] == ["documents.search"]
    assert answer.citations


async def test_step_limit() -> None:
    model = FakeModel(replies=[search("a", "1"), search("b", "2"), search("c", "3")])
    rig = await make_rig(
        model, results={"documents.search": doc_result("KYC Policy", "4.2")}, max_steps=3
    )

    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    assert events[-1] == Failed("step_limit")
    assert len(model.calls) == 3


async def test_role_cannot_use_a_restricted_feature() -> None:
    rig = await make_rig(FakeModel())
    with pytest.raises(PolicyDenied):
        await collect_events(rig.orchestrator.ask(teller(), uuid4(), "summary", "customer_360"))
    assert rig.conversations.messages == {}


async def test_record_lookup_cites_the_record() -> None:
    call = ToolCall("1", "transactions.get_status", {"query": "TX-0002"})
    model = FakeModel(replies=[ModelReply(None, (call,)), ModelReply("It failed: account closed.")])
    result = record_result("Transaction", "TX-0002", {"status": "failed"})
    rig = await make_rig(model, results={"transactions.get_status": result})

    answer = await final_answer(
        rig.orchestrator.ask(teller(), uuid4(), "Why did TX-0002 fail?", "transaction_lookup")
    )

    assert answer.citations == (Citation("record", "Transaction", "TX-0002"),)


async def test_router_picks_the_feature_when_none_is_given() -> None:
    model = FakeModel(
        replies=[
            ModelReply("transaction_lookup"),
            ModelReply(None, (ToolCall("1", "transactions.get_status", {"query": "TX-1"}),)),
            ModelReply("Completed."),
        ]
    )
    result = record_result("Transaction", "TX-1", {"status": "completed"})
    rig = await make_rig(model, results={"transactions.get_status": result})

    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "status of TX-1?"))

    assert events[0] == FeatureSelected("transaction_lookup")
    assert model.calls[0].tools == []  # routing is never given tools


async def test_history_and_answer_are_stored() -> None:
    model = FakeModel(replies=[search("kyc"), ModelReply("First answer.")])
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})
    conversation_id = uuid4()

    await final_answer(rig.orchestrator.ask(teller(), conversation_id, "kyc?", "policy_qa"))

    stored = rig.conversations.messages[conversation_id]
    assert [s.message.role for s in stored] == ["user", "assistant"]
    assert stored[1].feature_id == "policy_qa"
    assert stored[1].citations == (Citation("document", "KYC Policy", "4.2"),)


async def test_history_is_sent_to_the_model_on_the_next_turn() -> None:
    model = FakeModel(
        replies=[
            search("kyc"),
            ModelReply("First answer."),
            search("kyc", "2"),
            ModelReply("Second."),
        ]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})
    conversation_id = uuid4()

    await final_answer(rig.orchestrator.ask(teller(), conversation_id, "first?", "policy_qa"))
    await final_answer(rig.orchestrator.ask(teller(), conversation_id, "second?", "policy_qa"))

    second_turn = model.calls[2].messages
    assert [m.role for m in second_turn] == ["system", "user", "assistant", "user"]
    assert second_turn[-1] == Message("user", "second?")
    assert "Search documents first." in second_turn[0].content


async def test_model_unavailable_fails_the_turn_cleanly() -> None:
    class DownModel(FakeModel):
        async def chat(self, messages, tools):
            raise ModelUnavailable("timeout")

    rig = await make_rig(DownModel())
    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))
    assert events[-1] == Failed("model_unavailable")


async def test_audit_trail_for_a_turn() -> None:
    model = FakeModel(replies=[search("kyc"), ModelReply("Answer.")])
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    await final_answer(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))

    assert rig.audit.names() == [
        "question_asked",
        "feature_routed",
        "tool_called",
        "answer_returned",
    ]
    assert all(caller == teller() for caller, _, _ in rig.audit.events)


def test_teller_helper_is_a_staff_caller() -> None:
    assert teller() == Caller("S001", "teller", "staff", {"branch": "ACC-01"})
