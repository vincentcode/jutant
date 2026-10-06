"""Follow-ups and quick actions: a preferred feature is kept unless the question clearly belongs
elsewhere, a follow-up reads the previous question, and a question missing what the lookups need
is answered with the feature's question for it."""

from dataclasses import replace
from uuid import uuid4

import pytest

from core.events import FeatureSelected, TextDelta
from core.features.followup import Previous, is_follow_up, lookup_text, previous
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.types import ArgumentSource, Caller, Message, ModelReply, Prefetch, ToolCall
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

STATUS_BY_REFERENCE = Prefetch(
    "transactions.get_status", {"reference": ArgumentSource(match=r"\b(TX-\d+)\b")}
)
WHICH_TRANSFER = "Which transfer? Give me its reference."
SPECS = [
    spec("documents.search"),
    spec(
        "transactions.get_status",
        {
            "type": "object",
            "properties": {"reference": {"type": "string"}},
            "required": ["reference"],
        },
    ),
]


class TopicModel(FakeModel):
    """Embeds a text as the topic words it contains, so similarity is predictable."""

    TOPICS = ("transfer", "policy", "card", "id")

    async def embed(self, texts):
        return [[1.0 if t in text.lower() else 0.0 for t in self.TOPICS] for text in texts]


def features(**changes_by_id) -> tuple:
    return tuple(
        replace(f, **changes_by_id[f.id]) if f.id in changes_by_id else f for f in FEATURES
    )


EXAMPLES = features(
    policy_qa={"route_examples": ("What does the policy say?",)},
    transaction_lookup={
        "route_examples": ("Why did the transfer fail?",),
        "route_patterns": (r"\bTX-\d+\b",),
        "prefetch": (STATUS_BY_REFERENCE,),
    },
)


# --- what counts as a follow-up -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["TX-0002", "Why did it fail?", "and for joint accounts?", "What about the savings one?"],
)
def test_follow_ups(text: str) -> None:
    assert is_follow_up(text)


@pytest.mark.parametrize(
    "text",
    [
        "What ID do joint account holders need?",
        "Are there any penalties for breaking the circular?",
        "Give me a summary of customer C1001.",
    ],
)
def test_questions_that_stand_alone(text: str) -> None:
    assert not is_follow_up(text)


def test_previous_is_the_last_question_and_the_feature_that_answered() -> None:
    history = [
        Message("user", "Status of TX-0002?"),
        Message("assistant", "It failed.", feature_id="transaction_lookup"),
    ]
    assert previous(history) == Previous("Status of TX-0002?", "transaction_lookup")


def test_a_follow_up_looks_things_up_with_the_previous_question_after_its_own() -> None:
    before = Previous("Status of TX-0002?", "transaction_lookup")
    assert lookup_text("Why did it fail?", before) == "Why did it fail?\nStatus of TX-0002?"
    assert lookup_text("What ID do joint holders need?", before) == "What ID do joint holders need?"


# --- routing with a preferred feature -------------------------------------------------------


def router(model: FakeModel, feats=EXAMPLES) -> FeatureRouter:
    return FeatureRouter(model, FeatureRegistry(feats), default="policy_qa")


async def test_an_unclear_question_stays_with_the_preferred_feature_without_the_model() -> None:
    model = TopicModel()
    route = await router(model).route(teller(), "And yesterday's?", prefer="transaction_lookup")
    assert route.feature.id == "transaction_lookup" and route.by == "preferred"
    assert model.calls == []  # the model is not asked to choose


async def test_a_clearly_different_question_leaves_the_preferred_feature() -> None:
    route = await router(TopicModel()).route(
        teller(), "What does the policy require?", prefer="transaction_lookup"
    )
    assert route.feature.id == "policy_qa" and route.by == "meaning"


async def test_another_features_pattern_leaves_the_preferred_feature() -> None:
    route = await router(TopicModel()).route(teller(), "TX-0002 please", prefer="policy_qa")
    assert route.feature.id == "transaction_lookup" and route.by == "pattern"


async def test_a_preference_the_role_may_not_use_is_ignored() -> None:
    model = TopicModel(replies=[ModelReply("policy_qa")])
    route = await router(model).route(teller(), "Anything else?", prefer="customer_360")
    assert route.feature.id != "customer_360" and route.by != "preferred"


# --- the orchestrator -----------------------------------------------------------------------


async def test_a_switch_from_the_quick_action_is_announced() -> None:
    model = TopicModel(
        replies=[
            ModelReply(None, (ToolCall("1", "documents.search", {"query": "policy"}),)),
            ModelReply("The policy says..."),
        ]
    )
    rig = await make_rig(
        model, results={"documents.search": doc_result("KYC Policy", "4.2")}, features=EXAMPLES
    )
    events = await collect_events(
        rig.orchestrator.ask(
            teller(),
            uuid4(),
            "What does the policy require?",
            preferred_feature_id="transaction_lookup",
        )
    )
    assert events[0] == FeatureSelected("policy_qa", switched_from="transaction_lookup")


async def test_staying_with_the_quick_action_announces_no_switch() -> None:
    model = TopicModel(replies=[ModelReply("It failed: account closed.")])
    rig = await make_rig(
        model,
        results={"transactions.get_status": record_result("Transaction", "TX-0002", {})},
        specs=SPECS,
        features=EXAMPLES,
    )
    events = await collect_events(
        rig.orchestrator.ask(
            teller(), uuid4(), "Why did TX-0002 fail?", preferred_feature_id="transaction_lookup"
        )
    )
    assert events[0] == FeatureSelected("transaction_lookup")


async def test_a_question_without_a_reference_is_asked_for_one_without_the_model() -> None:
    asks = features(
        transaction_lookup={"prefetch": (STATUS_BY_REFERENCE,), "ask_for": WHICH_TRANSFER}
    )
    model = FakeModel()
    rig = await make_rig(model, features=asks)
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Why did the transfer fail?", "transaction_lookup")
    )
    assert [e.text for e in events if isinstance(e, TextDelta)] == [WHICH_TRANSFER]
    assert events[-1].answer.text == WHICH_TRANSFER  # not "no source found"
    assert model.calls == [] and rig.tools.calls == []


async def test_a_follow_up_stays_on_the_feature_and_finds_the_earlier_reference() -> None:
    model = TopicModel(replies=[ModelReply("It failed."), ModelReply("The account was closed.")])
    rig = await make_rig(
        model,
        results={"transactions.get_status": record_result("Transaction", "TX-0002", {})},
        specs=SPECS,
        features=EXAMPLES,
    )
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Status of TX-0002?", "transaction_lookup")
    )
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "Why did it fail?"))

    assert events[0] == FeatureSelected("transaction_lookup")
    assert [c.call.arguments for c in rig.tools.calls] == [{"reference": "TX-0002"}] * 2


async def test_a_summary_does_not_keep_its_follow_ups() -> None:
    # The follow-up is routed afresh (here by the model), not summarised again.
    model = FakeModel(
        replies=[
            ModelReply("Summary of the circular."),
            ModelReply("Summary of the circular."),  # after the nudge to use tools
            ModelReply("policy_qa"),  # routing the follow-up
            ModelReply(None, (ToolCall("1", "documents.search", {"query": "approve"}),)),
            ModelReply("A branch manager approves it."),
        ]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("Circular 14", "3")})
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Summarise circular 14", "extraction")
    )
    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Who has to approve it?")
    )
    assert events[0] == FeatureSelected("policy_qa")


async def test_a_quick_action_differing_from_a_running_procedure_ends_it() -> None:
    model = FakeModel(replies=[ModelReply("blocked_card")])
    rig = await make_rig(model)
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Card blocked", "troubleshooting")
    )
    assert await rig.playbooks.get_run(conversation) is not None

    model.replies = [
        ModelReply(None, (ToolCall("1", "documents.search", {"query": "kyc"}),)),
        ModelReply("Answer."),
    ]
    await collect_events(
        rig.orchestrator.ask(
            Caller("S1", "teller", "staff", {}),
            conversation,
            "KYC rules?",
            preferred_feature_id="policy_qa",
        )
    )
    assert await rig.playbooks.get_run(conversation) is None


# Real embeddings score most features 0.7-0.8, so "clearly ahead" is rare. Here policy_qa is
# closer (0.71) but not similar enough to decide alone.
async def test_a_quick_action_that_looks_wrong_is_routed_afresh() -> None:
    model = TopicModel(replies=[ModelReply("policy_qa")])
    route = await router(model).route(
        teller(), "Which policy covers a card?", prefer="transaction_lookup"
    )
    assert route.feature.id == "policy_qa" and route.by == "model"


async def test_a_follow_up_stays_unless_another_feature_is_clearly_closer() -> None:
    model = TopicModel()
    route = await router(model).route(
        teller(), "Which policy covers a card?", continuing="transaction_lookup"
    )
    assert route.feature.id == "transaction_lookup" and route.by == "preferred"
    assert model.calls == []


async def test_follow_ups_go_where_the_pack_sends_them() -> None:
    search_the_question = Prefetch("documents.search", {"query": ArgumentSource(question=True)})
    sends = features(
        extraction={"follow_ups": "policy_qa"}, policy_qa={"prefetch": (search_the_question,)}
    )
    model = TopicModel(
        replies=[
            ModelReply("Summary."),
            ModelReply("Summary."),  # after the nudge to use tools
            ModelReply("A branch manager approves it."),
        ]
    )
    rig = await make_rig(
        model, results={"documents.search": doc_result("Circular 14", "3")}, features=sends
    )
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Summarise circular 14", "extraction")
    )
    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation, "Who has to approve it?")
    )
    assert events[0] == FeatureSelected("policy_qa")
    # The search reads the summary's question too, so it finds the circular.
    assert rig.tools.calls[-1].call.arguments == {
        "query": "Who has to approve it?\nSummarise circular 14"
    }
