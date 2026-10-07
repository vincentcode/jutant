"""The conversation context: a stack of subjects, read each turn.

Units (entities, the stack, the certain readings, the model's reading), then whole
conversations through the orchestrator: follow-ups use the subject's entities, a detour keeps
the earlier subject, returning to it brings its entities back, a new subject never takes another
subject's, and a procedure waits below a side question until staff return to it.
"""

from dataclasses import replace
from uuid import uuid4

import pytest

from core.context import DOCUMENT, ContextStack, entities_in, from_calls, names_in, values_in
from core.context.reader import Reading, certain, read, same_subject
from core.context.stack import MAX_FRAMES, STALE_TURNS
from core.events import (
    Completed,
    FeatureSelected,
    PlaybookStepShown,
    ReplyUnclear,
    SubjectUnclear,
    TextDelta,
)
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.types import (
    ArgumentSource,
    Citation,
    EntityType,
    ModelReply,
    PlaybookStep,
    Prefetch,
    StepLookup,
    ToolCall,
)
from providers.llm.fake import FakeModel
from tests.builders import (
    BLOCKED_CARD,
    FEATURES,
    collect_events,
    doc_result,
    make_rig,
    record_result,
    spec,
    teller,
)

TYPES = (
    EntityType("transfer", r"(?i)\b(TX-\d+)\b"),
    EntityType("account", r"\b(\d{10})\b"),
)
STATUS = Prefetch("transactions.get_status", {"reference": ArgumentSource(entity="transfer")})
SEARCH = Prefetch("documents.search", {"query": ArgumentSource(question=True)})
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
    policy_qa={"route_examples": ("What does the policy say?",), "prefetch": (SEARCH,)},
    transaction_lookup={
        "route_examples": ("Why did the transfer fail?",),
        "route_patterns": (r"\bTX-\d+\b",),
        "prefetch": (STATUS,),
        "ask_for": WHICH_TRANSFER,
    },
)


def shown(events) -> list[int]:
    return [e.step.order for e in events if isinstance(e, PlaybookStepShown)]


def texts(events) -> list[str]:
    return [e.text for e in events if isinstance(e, TextDelta)]


async def bank(*replies: ModelReply, feats=EXAMPLES):
    """A rig with transfers that look up by entity, and its conversation."""
    model = TopicModel(replies=list(replies))
    rig = await make_rig(
        model,
        results={
            "transactions.get_status": record_result("Transaction", "TX-0002", {}),
            "documents.search": doc_result("KYC Policy", "4.2"),
        },
        specs=SPECS,
        features=feats,
        entity_types=TYPES,
    )
    return rig, model, uuid4()


async def ask(rig, conversation, text, *args, **kwargs):
    return await collect_events(rig.orchestrator.ask(teller(), conversation, text, *args, **kwargs))


def statuses(rig) -> list[str]:
    return [
        c.call.arguments["reference"] for c in rig.tools.calls if "reference" in c.call.arguments
    ]


async def stack_of(rig, conversation) -> ContextStack:
    return ContextStack.from_dict(await rig.conversations.context(conversation))


# --- entities -------------------------------------------------------------------------------


def test_entities_are_found_by_type() -> None:
    assert entities_in("Was tx-0007 from 0011223344?", TYPES) == {
        "transfer": "tx-0007",
        "account": "0011223344",
    }


def test_a_turn_looked_at_what_it_called_and_cited_not_what_it_said() -> None:
    found = from_calls(
        [ToolCall("1", "transactions.get_status", {"reference": "TX-0002"})],
        [Citation("record", "Transaction", "TX-0002"), Citation("document", "Error codes", "E51")],
        TYPES,
    )
    assert found == {"transfer": "TX-0002", DOCUMENT: "Error codes"}


# --- the stack ------------------------------------------------------------------------------


def test_a_detour_keeps_the_earlier_subject_and_returning_brings_it_back() -> None:
    stack = ContextStack()
    transfer = stack.push("transaction_lookup", {"transfer": "TX-0002"})
    stack.push("product_lookup", {"product": "SAV-STD"})
    assert stack.top.entities == {"product": "SAV-STD"}
    stack.bring_to_top(transfer.id)
    assert stack.top.entities == {"transfer": "TX-0002"} and len(stack.frames) == 2
    assert ContextStack.from_dict(stack.as_dict()) == stack  # kept between turns as data


def test_the_stack_keeps_five_subjects_and_drops_stale_ones() -> None:
    stack = ContextStack()
    for n in range(MAX_FRAMES + 2):
        stack.push("policy_qa", {"n": str(n)})
    assert len(stack.frames) == MAX_FRAMES and stack.top.entities == {"n": str(MAX_FRAMES + 1)}
    stack.turn += STALE_TURNS + 1
    stack.push("policy_qa")
    assert len(stack.frames) == 1


# --- certain readings -----------------------------------------------------------------------


def a_stack() -> ContextStack:
    stack = ContextStack()
    stack.push("transaction_lookup", {"transfer": "TX-0002"})
    stack.push("policy_qa")
    return stack


def test_without_a_subject_a_message_starts_one() -> None:
    assert certain(ContextStack(), "", {}, None, None) == Reading("new", by="first")


def test_naming_an_entity_returns_to_its_subject_without_the_model() -> None:
    stack = a_stack()
    earlier = stack.frames[1].id
    assert certain(stack, "", {"transfer": "TX-0002"}, None, None) == Reading(
        "return", earlier, by="entity"
    )
    assert certain(stack, "", {"transfer": "TX-0009"}, None, None) == Reading("new", by="entity")
    assert certain(stack, "", {}, None, None) is None  # names nothing: the model reads it


def test_staff_saying_what_a_message_is_decides_it() -> None:
    stack = a_stack()
    procedure = stack.push("troubleshooting", procedure=True)
    assert certain(stack, "", {}, "answer", None) == Reading("continue", procedure.id, by="staff")
    assert certain(stack, "", {}, "resume", None) == Reading("return", procedure.id, by="staff")
    assert certain(stack, "", {}, "stop", None) == Reading("stop", procedure.id, by="staff")
    assert certain(stack, "", {}, "question", None) == Reading("new", by="staff")
    assert certain(stack, "", {"transfer": "TX-0002"}, None, None) is None  # a step's reply: read
    assert certain(stack, "", {}, None, "troubleshooting") is None  # its own feature: read
    assert certain(stack, "", {}, None, "policy_qa").action == "new"  # another feature locked


# --- the model's reading --------------------------------------------------------------------


async def test_the_model_sees_the_subjects_and_picks_one() -> None:
    stack = a_stack()
    model = FakeModel(replies=[ModelReply("back_2")])
    reading = await read(model, "and the transfer?", stack, lambda f: f.feature_id, FEATURES)
    assert reading == Reading("return", stack.frames[1].id)
    prompt = model.calls[0].messages[0].content
    assert "1. policy_qa" in prompt and "2. transaction_lookup" in prompt


async def test_a_step_reply_names_its_option_and_an_unclear_one_gives_up() -> None:
    stack = ContextStack()
    procedure = stack.push("troubleshooting", procedure=True)
    step = BLOCKED_CARD.steps[1]  # choice: wrong_pin or fraud_hold
    model = FakeModel(replies=[ModelReply("fraud_hold"), ModelReply("hmm"), ModelReply("eh")])
    assert await read(model, "fraud block", stack, str, FEATURES, step) == Reading(
        "continue", procedure.id, choice="fraud_hold"
    )
    assert await read(model, "blue", stack, str, FEATURES, step) is None  # asked twice


# --- whole conversations --------------------------------------------------------------------


async def test_a_follow_up_uses_the_subjects_transfer() -> None:
    rig, _, conversation = await bank(
        ModelReply("It failed."), ModelReply("continue"), ModelReply("Closed.")
    )
    await ask(rig, conversation, "Why did TX-0002 fail?", "transaction_lookup")
    events = await ask(rig, conversation, "why did it fail?")
    assert events[-1].answer.text == "Closed."  # not "Which transfer?"
    assert statuses(rig) == ["TX-0002", "TX-0002"]


async def test_a_detour_and_back_restores_the_transfer() -> None:
    rig, _, conversation = await bank(
        ModelReply("It failed."),
        ModelReply("policy_qa"),  # reading: a new subject
        ModelReply("Two IDs."),
        ModelReply("back_2"),  # reading: back to the transfer
        ModelReply("It failed: account closed."),
    )
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    await ask(rig, conversation, "by the way, what ID do joint holders need?")
    events = await ask(rig, conversation, "ok, back to the transfer. what went wrong?")
    assert events[0] == FeatureSelected("transaction_lookup")
    assert statuses(rig) == ["TX-0002", "TX-0002"]
    stack = await stack_of(rig, conversation)
    assert [f.feature_id for f in stack.frames] == ["transaction_lookup", "policy_qa"]


async def test_a_new_subject_never_takes_another_subjects_entities() -> None:
    rig, _, conversation = await bank(ModelReply("It failed."))
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    # A new transfer subject (staff said it is a new question): TX-0002 is the other subject's.
    events = await ask(
        rig, conversation, "and the other transfer?", "transaction_lookup", reply_as="question"
    )
    assert texts(events) == [WHICH_TRANSFER]
    assert statuses(rig) == ["TX-0002"]  # looked up once, for its own subject


async def test_naming_the_entity_returns_without_asking_the_model() -> None:
    rig, model, conversation = await bank(
        ModelReply("It failed."),
        ModelReply("policy_qa"),
        ModelReply("Two IDs."),
        ModelReply("Account closed."),  # no reading call: TX-0002 names the subject
    )
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    await ask(rig, conversation, "what ID do joint holders need?")
    events = await ask(rig, conversation, "what was wrong with TX-0002?")
    assert events[0] == FeatureSelected("transaction_lookup") and not model.replies


async def test_a_question_beside_a_procedure_leaves_it_waiting_until_resumed() -> None:
    rig, _, conversation = await bank(
        ModelReply("done"),  # "customer verified" read as step 1 done
        ModelReply("policy_qa"),  # a side question
        ModelReply("Two IDs."),
    )
    await ask(rig, conversation, "card is blocked", "troubleshooting")
    assert shown(await ask(rig, conversation, "customer verified")) == [2]
    events = await ask(rig, conversation, "what ID do joint holders need?")
    assert shown(events) == [] and isinstance(events[-1], Completed)
    run = rig.playbooks.runs[conversation]
    assert run.status == "active" and run.paused and run.current_order == 2

    resumed = await ask(rig, conversation, "Resume the procedure", reply_as="resume")
    assert shown(resumed) == [2] and not rig.playbooks.runs[conversation].paused


async def test_stopping_the_procedure_says_so_and_drops_its_subject() -> None:
    rig, _, conversation = await bank(ModelReply("stop"))
    await ask(rig, conversation, "card is blocked", "troubleshooting")
    events = await ask(rig, conversation, "never mind, the customer left")
    assert texts(events) == ["Stopped the Blocked card procedure."]
    assert (await stack_of(rig, conversation)).frames == []


async def test_an_unclear_step_reply_asks_staff_and_keeps_nothing() -> None:
    rig, _, conversation = await bank(ModelReply("hmm"), ModelReply("still hmm"))
    await ask(rig, conversation, "card is blocked", "troubleshooting")
    before = (await stack_of(rig, conversation)).as_dict()
    events = await ask(rig, conversation, "blue")
    assert any(isinstance(e, ReplyUnclear) and e.step_order == 1 for e in events)
    assert (await stack_of(rig, conversation)).as_dict() == before


async def test_a_subject_without_its_entity_asks_for_it() -> None:
    rig, model, conversation = await bank()
    events = await ask(rig, conversation, "Why did the transfer fail?", "transaction_lookup")
    assert texts(events) == [WHICH_TRANSFER] and model.calls == []


async def test_a_summarys_follow_up_is_answered_from_the_document() -> None:
    feats = features(extraction={"follow_ups": "policy_qa"}, policy_qa={"prefetch": (SEARCH,)})
    rig, _, conversation = await bank(
        ModelReply("Summary."),
        ModelReply("Summary."),  # after the nudge to use tools
        ModelReply("continue"),  # reading: more about the summary
        ModelReply("A branch manager approves it."),
        feats=feats,
    )
    # The summary cited the circular: a document the follow-up's search then reads.
    rig.tools.results["documents.get"] = doc_result("Circular 14", "3")
    await ask(rig, conversation, "Summarise circular 14", "extraction")
    stack = await stack_of(rig, conversation)
    stack.put(stack.top.with_entities({DOCUMENT: "Circular 14"}))
    await rig.conversations.save_context(conversation, stack.as_dict())

    events = await ask(rig, conversation, "Who has to approve it?")
    assert events[0] == FeatureSelected("policy_qa")
    assert rig.tools.calls[-1].call.arguments == {"query": "Who has to approve it?\nCircular 14"}


# --- staff's quick action (router) ----------------------------------------------------------


def router(model: FakeModel, feats=EXAMPLES) -> FeatureRouter:
    return FeatureRouter(model, FeatureRegistry(feats), default="policy_qa")


async def test_an_unclear_question_stays_with_the_quick_action_without_the_model() -> None:
    model = TopicModel()
    route = await router(model).route(teller(), "And yesterday's?", prefer="transaction_lookup")
    assert route.feature.id == "transaction_lookup" and route.by == "preferred"
    assert model.calls == []


async def test_a_clearly_different_question_leaves_the_quick_action() -> None:
    route = await router(TopicModel()).route(
        teller(), "What does the policy require?", prefer="transaction_lookup"
    )
    assert route.feature.id == "policy_qa" and route.by == "meaning"


async def test_another_features_pattern_leaves_the_quick_action() -> None:
    route = await router(TopicModel()).route(teller(), "TX-0002 please", prefer="policy_qa")
    assert route.feature.id == "transaction_lookup" and route.by == "pattern"


async def test_a_quick_action_the_role_may_not_use_is_ignored() -> None:
    model = TopicModel(replies=[ModelReply("policy_qa")])
    route = await router(model).route(teller(), "Anything else?", prefer="customer_360")
    assert route.feature.id != "customer_360" and route.by != "preferred"


async def test_a_quick_action_that_looks_wrong_is_routed_afresh() -> None:
    model = TopicModel(replies=[ModelReply("policy_qa")])
    route = await router(model).route(
        teller(), "Which policy covers a card?", prefer="transaction_lookup"
    )
    assert route.feature.id == "policy_qa" and route.by == "model"


async def test_a_switch_from_the_quick_action_is_announced() -> None:
    rig, _, conversation = await bank(
        ModelReply("The policy says..."),
    )
    events = await ask(
        rig,
        conversation,
        "What does the policy require?",
        preferred_feature_id="transaction_lookup",
    )
    assert events[0] == FeatureSelected("policy_qa", switched_from="transaction_lookup")


@pytest.mark.parametrize("question", ["Why did TX-0002 fail?"])
async def test_staying_with_the_quick_action_announces_no_switch(question) -> None:
    rig, _, conversation = await bank(ModelReply("It failed: account closed."))
    events = await ask(rig, conversation, question, preferred_feature_id="transaction_lookup")
    assert events[0] == FeatureSelected("transaction_lookup")


# --- names, the reader's feature options, and returning by a click --------------------------

NAMED = (*TYPES, EntityType("product", r"\b([A-Z]{3}-[A-Z]{3})\b", name_field="name"))


def test_names_are_learned_from_results_and_found_in_messages() -> None:
    learned = names_in(
        [
            {"code": "SAV-STD", "name": "Standard Savings"},
            {"code": "CUR-BIZ", "name": "Business Current"},
        ],
        NAMED,
    )
    assert learned == {
        "standard savings": ("product", "SAV-STD"),
        "business current": ("product", "CUR-BIZ"),
    }
    assert entities_in("and the Standard Savings rate?", NAMED, learned) == {"product": "SAV-STD"}
    assert names_in({"reference": "TX-0002", "narration": "Transfer"}, NAMED) == {}  # no name field


def test_a_known_name_returns_to_its_subject_without_the_model() -> None:
    stack = ContextStack()
    savings = stack.push("product_lookup", {"product": "SAV-STD"})
    stack.push("product_lookup", {"product": "CUR-BIZ"})
    stack.learn({"standard savings": ("product", "SAV-STD")})
    mentioned = entities_in("what was the Standard Savings rate again?", NAMED, stack.names)
    assert certain(stack, "", mentioned, None, None) == Reading("return", savings.id, by="entity")


async def test_choosing_the_current_subjects_feature_is_a_new_subject() -> None:
    # "and what's the Standard Savings rate?" after Business Current: a new product, which must
    # not take Business Current's code (the development set's DEVIATION-006).
    stack = ContextStack()
    stack.push("transaction_lookup", {"transfer": "TX-0002"})
    model = FakeModel(replies=[ModelReply("transaction_lookup")])
    assert await read(model, "and the other one?", stack, str, FEATURES) == Reading(
        "new", feature_id="transaction_lookup"
    )


async def test_clicking_a_subject_returns_to_it_without_the_model() -> None:
    rig, model, conversation = await bank(
        ModelReply("It failed."), ModelReply("policy_qa"), ModelReply("Two IDs.")
    )
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    await ask(rig, conversation, "what ID do joint holders need?")
    transfer = next(
        id_ for id_, title, _ in await rig.orchestrator.subjects(conversation) if "TX-0002" in title
    )
    calls = len(model.calls)
    events = await ask(
        rig, conversation, "Back to the transfer", reply_as="return", subject_id=transfer
    )
    assert texts(events) == [
        "Back to Transaction lookup: transfer TX-0002. What would you like to know?"
    ]
    assert len(model.calls) == calls  # no model
    assert (await stack_of(rig, conversation)).top.id == transfer


# --- structural fixes: same kind or another, one procedure, steps, the case, records ---------

LOOKS_UP = PlaybookStep(
    1,
    "Reference",
    "Enter the reference.",
    ("staff",),
    "text",
    lookup=StepLookup("transactions.get_status", "reference", r"(?i)\b(TX-\d+)\b"),
)


def test_a_reply_a_lookup_step_can_take_is_its_answer_without_the_model() -> None:
    stack = ContextStack()
    procedure = stack.push("troubleshooting", procedure=True)
    assert certain(stack, "it is TX-0002", {"transfer": "TX-0002"}, None, None, step=LOOKS_UP) == (
        Reading("continue", procedure.id, by="step")
    )
    assert certain(stack, "what is a reference?", {}, None, None, step=LOOKS_UP) is None


async def test_another_of_the_same_kind_or_the_same_one_is_asked_as_a_second_question() -> None:
    model = FakeModel(replies=[ModelReply("same"), ModelReply("different")])
    assert await same_subject(model, "how much is the fee?", "product CUR-BIZ") is True
    assert await same_subject(model, "and Standard Savings?", "product CUR-BIZ") is False
    assert "product CUR-BIZ" in model.calls[0].messages[0].content


async def test_the_same_subject_keeps_its_entities_and_another_starts_empty() -> None:
    rig, _, conversation = await bank(
        ModelReply("It failed."),
        ModelReply("transaction_lookup"),  # reading: the transfer feature again...
        ModelReply("same"),  # ...about the same transfer
        ModelReply("Account closed."),
    )
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    events = await ask(rig, conversation, "why did it fail?")
    assert events[-1].answer.text == "Account closed." and statuses(rig) == ["TX-0002"] * 2


async def test_when_neither_can_tell_staff_are_asked_which_subject() -> None:
    rig, _, conversation = await bank(
        ModelReply("It failed."),
        ModelReply("transaction_lookup"),
        ModelReply("hmm"),
        ModelReply("eh"),  # the second question, asked twice, unclear
        ModelReply("Account closed."),
    )
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    before = (await stack_of(rig, conversation)).as_dict()
    events = await ask(rig, conversation, "why did it fail?")
    [unclear] = [e for e in events if isinstance(e, SubjectUnclear)]
    assert texts(events) == [f"Is this about {unclear.subject_title}, or something new?"]
    assert (await stack_of(rig, conversation)).as_dict() == before  # nothing kept

    answered = await ask(
        rig, conversation, "why did it fail?", reply_as="continue", subject_id=unclear.subject_id
    )
    assert answered[-1].answer.text == "Account closed." and statuses(rig) == ["TX-0002"] * 2


async def test_no_second_procedure_starts_while_one_is_open() -> None:
    stack = ContextStack()
    stack.push("troubleshooting", procedure=True)
    model = TopicModel(replies=[ModelReply("policy_qa")])
    route = await router(model).route(
        teller(), "can i just replace the card?", exclude=("troubleshooting",)
    )
    assert route.feature.id != "troubleshooting"
    prompt_features = [f for f in FEATURES if f.template != "guided_playbook"]
    reading = await read(
        FakeModel(replies=[ModelReply("troubleshooting"), ModelReply("policy_qa")]),
        "can i just replace the card?",
        stack,
        str,
        prompt_features,
        BLOCKED_CARD.steps[0],
    )
    assert reading == Reading("new", feature_id="policy_qa")  # troubleshooting was not offered


async def test_a_question_beside_a_case_takes_only_what_its_lookups_use() -> None:
    rig, _, _ = await bank()
    orchestrator = rig.orchestrator
    stack = ContextStack()
    case = stack.push("transaction_lookup", {"transfer": "TX-0002", "account": "0011223344"})
    stack.put(case.with_related({"error_code": "E51"}))
    explains = replace(
        FEATURES[0],
        id="code_explainer",
        prefetch=(Prefetch("documents.search", {"query": ArgumentSource(entity="error_code")}),),
    )
    assert orchestrator._case(stack, None, explains) == {"error_code": "E51"}
    same_kind = replace(FEATURES[1], prefetch=(STATUS,))
    assert orchestrator._case(stack, None, same_kind) == {}  # another transfer takes nothing


def test_a_record_points_only_with_exact_ids() -> None:
    record = {"reference": "TX-0002", "narration": "Transfer to 5566778899", "code": "E51"}
    types = (*TYPES, EntityType("error_code", r"\b([A-Z]\d{2,3})\b"))
    assert values_in(record, types) == {"transfer": "TX-0002", "error_code": "E51"}
    assert values_in([record], types) == {}  # a list: which one is meant is not known


async def test_a_second_prefetch_round_follows_what_the_record_points_to() -> None:
    explained = replace(
        EXAMPLES[1],
        tools=("transactions.get_status", "documents.search"),
        prefetch=(
            STATUS,
            Prefetch("documents.search", {"query": ArgumentSource(entity="error_code")}),
        ),
    )
    feats = tuple(explained if f.id == explained.id else f for f in EXAMPLES)
    rig, _, conversation = await bank(ModelReply("Closed; returned in two days."), feats=feats)
    rig.tools.results["transactions.get_status"] = record_result(
        "Transaction", "TX-0002", {"failure_code": "E51"}
    )
    rig.orchestrator.entity_types = (*TYPES, EntityType("error_code", r"\b([A-Z]\d{2,3})\b"))
    await ask(rig, conversation, "check TX-0002", "transaction_lookup")
    assert [c.call.name for c in rig.tools.calls] == ["transactions.get_status", "documents.search"]
    assert rig.tools.calls[1].call.arguments == {"query": "E51"}


async def test_a_checklist_reads_the_documents_too() -> None:
    from core.features.templates.checklist import ChecklistTemplate

    checklist = replace(
        FEATURES[0], id="forms", template="checklist", tools=("documents.search",), prefetch=()
    )
    rig, _, conversation = await bank(ModelReply("Sign the joint mandate."), feats=(checklist,))
    await ask(rig, conversation, "who signs the mandate?", "forms")
    assert rig.tools.calls[0].call.arguments == {"query": "who signs the mandate?"}
    assert ChecklistTemplate.id == "checklist"
