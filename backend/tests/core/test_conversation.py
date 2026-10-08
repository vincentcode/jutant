"""Talking with staff: no sources, the kinds of help offered as tools the model may hand the
turn to, staff asked to pick when it cannot tell, small talk that does not become a subject of
the conversation, and the agent turn mode."""

from uuid import uuid4

from core.context import ContextStack
from core.events import Clarify, Completed, FeatureSelected, HandOver, TextDelta
from core.types import Feature, ModelReply, ToolCall
from providers.llm.fake import FakeModel
from tests.builders import (
    FEATURES,
    collect_events,
    doc_result,
    make_rig,
    record_result,
    teller,
)

TALK = Feature(
    "conversation",
    "conversation",
    "General conversation",
    "Greetings, thanks, what the assistant can help with.",
    "Talk with staff.",
    (),
    (),
)
WITH_TALK = (*FEATURES, TALK)


async def stack_of(rig, conversation) -> ContextStack:
    return ContextStack.from_dict(await rig.conversations.context(conversation))


async def test_a_greeting_is_answered_without_tools_or_sources() -> None:
    model = FakeModel(replies=[ModelReply("Hello! I can look up transfers and policies.")])
    rig = await make_rig(model, features=WITH_TALK)
    conversation = uuid4()
    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Hello, what can you do?", "conversation")
    )
    assert isinstance(events[-1], Completed)
    assert events[-1].answer.text == "Hello! I can look up transfers and policies."  # kept
    assert rig.tools.calls == []
    offered = [t.name for t in model.calls[0].tools]  # the kinds of help, not their tools
    assert "transaction_lookup" in offered and "ask_which" in offered
    assert "conversation" not in offered and "customer_360" not in offered  # not a teller's
    assert (await stack_of(rig, conversation)).frames == []  # not a subject


async def test_small_talk_leaves_the_subject_staff_were_on() -> None:
    model = FakeModel(
        replies=[
            ModelReply("It failed."),
            ModelReply("It failed."),  # after the nudge to use tools
            ModelReply("conversation"),  # reading "thanks": talk
            ModelReply("You're welcome."),
        ]
    )
    rig = await make_rig(
        model,
        results={"transactions.get_status": record_result("Transaction", "TX-0002", {})},
        features=WITH_TALK,
    )
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Why did TX-0002 fail?", "transaction_lookup")
    )
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "thanks!"))
    assert events[-1].answer.text == "You're welcome."
    stack = await stack_of(rig, conversation)
    assert [f.feature_id for f in stack.frames] == ["transaction_lookup"]


async def test_a_word_in_passing_does_not_leave_a_procedure_paused() -> None:
    model = FakeModel(replies=[ModelReply("conversation"), ModelReply("Of course.")])
    rig = await make_rig(model, features=WITH_TALK)
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "card is blocked", "troubleshooting")
    )
    await collect_events(rig.orchestrator.ask(teller(), conversation, "one moment please"))
    run = rig.playbooks.runs[conversation]
    assert run.status == "active" and not run.paused
    assert (await stack_of(rig, conversation)).top.procedure


def call(name: str, **arguments: object) -> ModelReply:
    return ModelReply(None, (ToolCall("c1", name, dict(arguments)),))


async def test_the_conversation_hands_a_request_to_the_feature_it_chose() -> None:
    model = FakeModel(
        replies=[
            call("transaction_lookup"),
            call("transactions.get_status", query="TX-0002"),
            ModelReply("It failed: insufficient funds."),
        ]
    )
    rig = await make_rig(
        model,
        results={"transactions.get_status": record_result("Transaction", "TX-0002", {})},
        features=WITH_TALK,
        default="conversation",
    )
    conversation = uuid4()
    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation, "A payment is off", "conversation")
    )
    selected = [e.feature_id for e in events if isinstance(e, FeatureSelected)]
    assert selected == ["transaction_lookup"]  # the conversation never answered
    assert not any(isinstance(e, HandOver) for e in events)
    assert events[-1].answer.text == "It failed: insufficient funds."
    assert [c.call.name for c in rig.tools.calls] == ["transactions.get_status"]
    stored = await rig.conversations.recent_messages(conversation, 10)
    assert [m.role for m in stored] == ["user", "assistant"]  # the question stored once
    assert [f.feature_id for f in (await stack_of(rig, conversation)).frames] == [
        "transaction_lookup"
    ]
    routed = [d for _, name, d in rig.audit.events if name == "feature_routed"]
    assert routed[-1]["chosen_by"] == "model:hand_over"


async def test_when_it_cannot_tell_staff_pick_from_the_kinds_of_help() -> None:
    model = FakeModel(replies=[call("ask_which", options=["policy_qa", "troubleshooting", "x"])])
    rig = await make_rig(model, features=WITH_TALK, default="conversation")
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "the card thing", "conversation")
    )
    offered = next(e for e in events if isinstance(e, Clarify))
    assert [(c.kind, c.feature_id, c.title) for c in offered.choices] == [
        ("feature", "policy_qa", "Policy Q&A"),
        ("feature", "troubleshooting", "Troubleshooting"),
    ]
    assert events[-1].answer.text == "Which of these do you need?"


async def test_a_call_to_no_offered_tool_is_retried_then_every_kind_of_help_offered() -> None:
    model = FakeModel(replies=[call("documents.search"), call("make_coffee")])
    rig = await make_rig(model, features=WITH_TALK, default="conversation")
    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "hmm", "conversation"))
    assert model.calls[1].messages[-1].role == "tool"  # told, once
    offered = next(e for e in events if isinstance(e, Clarify))
    assert [c.feature_id for c in offered.choices] == [
        "policy_qa",
        "transaction_lookup",
        "troubleshooting",
        "extraction",
    ]


async def test_a_procedure_is_not_offered_while_one_is_open() -> None:
    model = FakeModel(replies=[ModelReply("new"), ModelReply("Sure, ask away.")])
    rig = await make_rig(model, features=WITH_TALK, default="conversation", turn_mode="agent")
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "card is blocked", "troubleshooting")
    )
    await collect_events(rig.orchestrator.ask(teller(), conversation, "can I ask something?"))
    offered = [t.name for t in model.calls[-1].tools]
    assert "troubleshooting" not in offered and "policy_qa" in offered


async def test_in_agent_mode_the_model_chooses_a_new_subjects_feature() -> None:
    model = FakeModel(
        replies=[
            call("policy_qa"),  # no routing first: the conversation sees the features as tools
            call("documents.search", query="ID for a new customer"),
            ModelReply("Two forms of ID."),
        ]
    )
    rig = await make_rig(
        model,
        results={"documents.search": doc_result("KYC policy", "3.1")},
        features=WITH_TALK,
        default="conversation",
        turn_mode="agent",
    )
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "What ID does a new customer need?")
    )
    assert model.calls[0].tools and model.calls[0].tools[0].name == "policy_qa"
    assert events[-1].answer.feature_id == "policy_qa"
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Two forms of ID."


async def test_in_agent_mode_the_reading_only_says_a_subject_is_new() -> None:
    model = FakeModel(replies=[ModelReply("new"), ModelReply("Hi again.")])
    rig = await make_rig(model, features=WITH_TALK, default="conversation", turn_mode="agent")
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "card is blocked", "troubleshooting")
    )
    await collect_events(rig.orchestrator.ask(teller(), conversation, "hello"))
    reading = model.calls[0].messages[0].content
    assert "new: a different subject" in reading and "policy_qa" not in reading


async def test_a_picker_and_the_pick_are_audited() -> None:
    model = FakeModel(replies=[call("ask_which", options=["policy_qa", "troubleshooting"])])
    rig = await make_rig(model, features=WITH_TALK, default="conversation")
    conversation = uuid4()
    await collect_events(rig.orchestrator.ask(teller(), conversation, "hmm", "conversation"))
    [shown] = [d for _, name, d in rig.audit.events if name == "clarify_shown"]
    assert shown["reason"] == "ask_which"
    assert [c["feature_id"] for c in shown["choices"]] == ["policy_qa", "troubleshooting"]

    rig.model.replies = [call("documents.search", query="ID"), ModelReply("Two forms of ID.")]
    rig.tools.results["documents.search"] = doc_result("KYC policy", "3.1")
    await collect_events(
        rig.orchestrator.ask(
            teller(), conversation, "hmm", "policy_qa", reply_as="question", picked=0
        )
    )
    asked = [d for _, name, d in rig.audit.events if name == "question_asked"]
    assert [d["picked"] for d in asked] == [None, 0]


async def test_talk_comes_with_the_kinds_of_help() -> None:
    model = FakeModel(replies=[ModelReply("Of course! What do you need help with?")])
    rig = await make_rig(model, features=WITH_TALK, default="conversation")
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "I need help with something", "conversation")
    )
    [asked] = [e for e in events if isinstance(e, Clarify)]
    assert asked.reason == "talk" and asked.question.endswith("help with?")
    assert "policy_qa" in [c.feature_id for c in asked.choices]
    assert events[-1].answer.text == "Of course! What do you need help with?"  # its own words


async def test_talk_that_asks_nothing_still_offers_the_kinds_of_help() -> None:
    model = FakeModel(replies=[ModelReply("Good evening! Let me know, and I'll guide you.")])
    rig = await make_rig(model, features=WITH_TALK, default="conversation")
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "good evening", "conversation")
    )
    [offered] = [e for e in events if isinstance(e, Clarify)]
    assert offered.reason == "talk" and len(offered.choices) == 4


async def test_in_hybrid_mode_an_unsure_question_goes_to_the_conversation() -> None:
    model = FakeModel(
        replies=[
            ModelReply("hmm, maybe one of those"),  # the router's model cannot choose...
            ModelReply("I can look up transfers and policies."),  # ...so the conversation talks
        ]
    )
    rig = await make_rig(model, features=WITH_TALK, default="conversation", turn_mode="hybrid")
    events = await collect_events(rig.orchestrator.ask(teller(), uuid4(), "what tools are there"))
    assert events[-1].answer.feature_id == "conversation"  # not the keywords' guess
    facts = model.calls[1].messages[1].content
    assert "The kinds of help you give:" in facts and "you cannot change anything" in facts
    routed = [d for _, name, d in rig.audit.events if name == "feature_routed"]
    assert routed[-1]["chosen_by"] == "unsure"
