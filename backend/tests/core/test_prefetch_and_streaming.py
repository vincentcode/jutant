"""Tool calls made in code before the model (prefetch), and answers streamed as written."""

from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import uuid4

from core.events import Event, Failed, TextDelta, ToolStarted
from core.orchestrator.orchestrator import NO_SOURCE_MESSAGE
from core.types import ArgumentSource, Citation, ModelReply, Prefetch, ToolCall, ToolResult
from providers.llm.fake import FakeModel
from tests.builders import (
    FEATURES,
    collect_events,
    doc_result,
    make_rig,
    record_result,
    spec,
    teller,
)

REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {"reference": {"type": "string"}},
    "required": ["reference"],
}


def features_with(feature_id: str, *prefetch: Prefetch):
    return tuple(replace(f, prefetch=prefetch) if f.id == feature_id else f for f in FEATURES)


SEARCH_THE_QUESTION = Prefetch("documents.search", {"query": ArgumentSource(question=True)})
STATUS_BY_REFERENCE = Prefetch(
    "transactions.get_status", {"reference": ArgumentSource(match=r"\b(TX-\d+)\b")}
)


def texts(events: list[Event]) -> list[str]:
    return [e.text for e in events if isinstance(e, TextDelta)]


async def test_a_prefetched_search_is_made_before_the_model_is_asked() -> None:
    model = FakeModel(replies=[ModelReply("Both holders must provide ID.")])
    rig = await make_rig(
        model,
        results={"documents.search": doc_result("KYC Policy", "4.2")},
        features=features_with("policy_qa", SEARCH_THE_QUESTION),
    )

    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "What ID do joint holders need?", "policy_qa")
    )

    assert rig.tools.calls[0].call.arguments == {"query": "What ID do joint holders need?"}
    assert len(model.calls) == 1  # the model only writes the answer
    seen = model.calls[0].messages
    assert seen[-2].tool_calls[0].name == "documents.search"  # as if the model had called it
    assert seen[-1].role == "tool" and "KYC Policy" in seen[-1].content
    assert events[-1].answer.citations == (Citation("document", "KYC Policy", "4.2"),)
    assert "tool_called" in [kind for _, kind, _ in rig.audit.events]  # through the gateway


async def test_a_value_matched_in_the_question_fills_the_argument() -> None:
    model = FakeModel(replies=[ModelReply("It failed.")])
    rig = await make_rig(
        model,
        results={"transactions.get_status": record_result("Transaction", "TX-0002", {})},
        specs=[spec("transactions.get_status", REFERENCE_SCHEMA)],
        features=features_with("transaction_lookup", STATUS_BY_REFERENCE),
    )
    await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Why did TX-0002 fail?", "transaction_lookup")
    )
    assert rig.tools.calls[0].call.arguments == {"reference": "TX-0002"}


async def test_no_match_means_no_prefetch_and_the_model_chooses() -> None:
    model = FakeModel(replies=[ModelReply("Which transfer?")])
    rig = await make_rig(
        model,
        specs=[spec("transactions.get_status", REFERENCE_SCHEMA)],
        features=features_with("transaction_lookup", STATUS_BY_REFERENCE),
    )
    model.replies.append(ModelReply("Please give the reference."))  # after the nudge
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Why did my transfer fail?", "transaction_lookup")
    )
    assert not any(isinstance(e, ToolStarted) for e in events)
    assert texts(events) == [NO_SOURCE_MESSAGE]


async def test_a_failed_prefetch_is_shown_to_the_model_and_nothing_is_invented() -> None:
    model = FakeModel(replies=[ModelReply("TX-0099 was not found.")])
    rig = await make_rig(
        model,
        results={"transactions.get_status": ToolResult("", ok=False, error="not_found")},
        specs=[spec("transactions.get_status", REFERENCE_SCHEMA)],
        features=features_with("transaction_lookup", STATUS_BY_REFERENCE),
    )
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Why did TX-0099 fail?", "transaction_lookup")
    )
    assert '"error":"not_found"' in model.calls[0].messages[-1].content
    assert texts(events) == [NO_SOURCE_MESSAGE]  # no source, so no answer


# --- streaming ----------------------------------------------------------------------------


async def test_a_cited_answer_streams_in_pieces() -> None:
    answer = "Each holder must provide a photo ID and proof of address."
    model = FakeModel(replies=[ModelReply(answer)])
    rig = await make_rig(
        model,
        results={"documents.search": doc_result("KYC Policy", "4.2")},
        features=features_with("policy_qa", SEARCH_THE_QUESTION),
    )
    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "ID?", "policy_qa"))

    pieces = [e for e in events if isinstance(e, TextDelta)]
    assert len(pieces) > 1 and not pieces[0].continues and all(p.continues for p in pieces[1:])
    assert "".join(p.text for p in pieces) == answer == events[-1].answer.text
    stored = rig.conversations.messages[next(iter(rig.conversations.messages))]
    assert stored[-1].message.content == answer


async def test_an_answer_without_a_source_is_never_streamed() -> None:
    model = FakeModel(replies=[ModelReply("From memory."), ModelReply("Still from memory.")])
    rig = await make_rig(model)
    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))
    assert texts(events) == [NO_SOURCE_MESSAGE]


async def test_separate_texts_are_separate_paragraphs() -> None:
    class TwoParagraphs:
        id = "two"
        requires_citation = False

        async def run(self, ctx) -> AsyncIterator[Event]:
            yield TextDelta("First.")
            yield TextDelta("Second ")
            yield TextDelta("part.", continues=True)

    rig = await make_rig(FakeModel())
    rig.orchestrator.templates = {**rig.orchestrator.templates, "document_qa": TwoParagraphs()}
    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "?", "policy_qa"))

    assert "".join(texts(events)) == "First.\n\nSecond part." == events[-1].answer.text


async def test_the_answer_record_says_where_the_time_went() -> None:
    model = FakeModel(replies=[ModelReply("Both holders must provide ID.")])
    rig = await make_rig(
        model,
        results={"documents.search": doc_result("KYC Policy", "4.2")},
        features=features_with("policy_qa", SEARCH_THE_QUESTION),
    )
    await collect_events(rig.orchestrator.ask(teller(), uuid4(), "ID?", "policy_qa"))

    [answered] = [d for _, kind, d in rig.audit.events if kind == "answer_returned"]
    timing = answered["timing"]
    assert timing["model_calls"] == 1  # prefetch saved the model's search step
    assert set(timing) == {"total_ms", "route_ms", "model_ms", "tool_ms", "embed_ms", "model_calls"}
    assert timing["total_ms"] >= timing["model_ms"] + timing["tool_ms"]


async def test_a_refused_prefetch_ends_the_turn_without_asking_the_model() -> None:
    model = FakeModel()  # no replies scripted: the model must not be called
    rig = await make_rig(
        model,
        results={"transactions.get_status": ToolResult("", ok=False, error="denied")},
        specs=[spec("transactions.get_status", REFERENCE_SCHEMA)],
        features=features_with("transaction_lookup", STATUS_BY_REFERENCE),
    )
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Why did TX-0002 fail?", "transaction_lookup")
    )
    assert isinstance(events[-1], Failed) and events[-1].reason == "denied"
    assert model.calls == []


async def test_a_refused_call_of_the_models_ends_the_turn() -> None:
    call = ModelReply(None, (ToolCall("1", "transactions.get_status", {"reference": "TX-1"}),))
    model = FakeModel(replies=[call])  # nothing after the call: no second model step
    rig = await make_rig(
        model,
        results={"transactions.get_status": ToolResult("", ok=False, error="denied")},
        specs=[spec("transactions.get_status", REFERENCE_SCHEMA)],
    )
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Status of my transfer?", "transaction_lookup")
    )
    assert events[-1] == Failed("denied") and len(model.calls) == 1
