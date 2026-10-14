"""Confirmed actions: the model proposes, code keeps the draft, only the person sends it."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from core.actions.drafts import read_draft
from core.actions.service import NOT_ANSWERED, REQUEST_ID
from core.actions.types import Action
from core.context import ContextStack
from core.context.reader import Reading, certain
from core.errors import ActionUnavailable
from core.events import ActionProposed, Completed, FeatureSelected, TextDelta, ToolFinished
from core.orchestrator.orchestrator import CHECK_THE_REQUEST
from core.types import Caller, Citation, Feature, ModelReply, ToolCall, ToolResult
from providers.llm.fake import FakeModel
from tests.builders import collect_events, make_rig, spec

LEAVE = Action(
    "leave_request", "Leave request", "leave.propose", "leave.submit", roles=("employee",)
)
MY_LEAVE = Feature(
    "my_leave",
    "record_lookup",
    "My leave",
    "Leave balance and requests.",
    "Help with leave.",
    ("leave.propose",),
    (),
)
DRAFT = {
    "summary": "Annual leave, 10-14 Nov 2026",
    "fields": [{"label": "From", "value": "Mon 10 Nov 2026"}, {"label": "Days", "value": 5}],
    "notes": ["Balance after this: 9 of 21 days"],
    "submit": {"type": "annual", "from": "2026-11-10", "to": "2026-11-14"},
}
OPEN = {"type": "object"}
PROPOSE = ModelReply(
    None, tool_calls=(ToolCall("1", "leave.propose", {"type": "annual", "from": "10 Nov"}),)
)


def employee(staff_id: str = "E100") -> Caller:
    return Caller(staff_id, "employee", "employee")


async def rig_for(results: dict, model: FakeModel | None = None):
    return await make_rig(
        model or FakeModel(replies=[PROPOSE, ModelReply("never used")]),
        results=results,
        specs=[spec("leave.propose", OPEN), spec("leave.submit", OPEN)],
        features=(MY_LEAVE,),
        default="my_leave",
        actions=(LEAVE,),
    )


async def propose(rig, caller: Caller | None = None):
    events = await collect_events(
        rig.orchestrator.ask(caller or employee(), uuid4(), "5 days off from 10 Nov", "my_leave")
    )
    return events


async def test_a_draft_ends_the_turn_with_a_card_and_nothing_sent() -> None:
    rig = await rig_for({"leave.propose": ToolResult("", ok=True, data=DRAFT)})
    events = await propose(rig)

    kinds = [type(e) for e in events]
    assert ActionProposed in kinds and kinds.index(ToolFinished) < kinds.index(ActionProposed)
    card = next(e for e in events if isinstance(e, ActionProposed)).proposal
    assert (card.title, card.status, card.draft.summary) == (
        "Leave request",
        "proposed",
        "Annual leave, 10-14 Nov 2026",
    )
    assert [(f.label, f.value) for f in card.draft.fields] == [
        ("From", "Mon 10 Nov 2026"),
        ("Days", "5"),
    ]
    assert len(rig.model.calls) == 1  # the model writes nothing after the draft
    assert [c.call.name for c in rig.tools.calls] == ["leave.propose"]  # nothing submitted
    assert [e.text for e in events if isinstance(e, TextDelta)] == [CHECK_THE_REQUEST]
    assert isinstance(events[-1], Completed)
    assert "action_proposed" in rig.audit.names()


async def test_a_refusal_goes_back_to_the_model_and_shows_no_card() -> None:
    model = FakeModel(replies=[PROPOSE, ModelReply("You have only 3 days left.")])
    rig = await rig_for(
        {
            "leave.propose": ToolResult(
                "",
                ok=True,
                data={"refused": "Only 3 days left"},
                citations=(Citation("record", "Leave balance", "E100"),),
            )
        },
        model,
    )
    events = await propose(rig)
    assert not any(isinstance(e, ActionProposed) for e in events)
    assert events[-1].answer.text == "You have only 3 days left."


async def test_a_role_the_action_is_not_for_gets_no_card() -> None:
    rig = await rig_for({"leave.propose": ToolResult("", ok=True, data=DRAFT)})
    events = await propose(rig, Caller("S1", "teller", "staff"))
    assert not any(isinstance(e, ActionProposed) for e in events)


async def test_confirming_sends_the_draft_as_shown_once() -> None:
    sent = ToolResult("", ok=True, data={"reference": "LV-1", "status": "Waiting for manager"})
    rig = await rig_for(
        {"leave.propose": ToolResult("", ok=True, data=DRAFT), "leave.submit": sent}
    )
    card = next(e for e in await propose(rig) if isinstance(e, ActionProposed)).proposal

    done = await rig.actions.confirm(employee(), card.id)

    assert (done.status, done.reference, done.outcome) == ("sent", "LV-1", "Waiting for manager")
    submit = rig.tools.calls[-1].call
    assert submit.name == "leave.submit"
    assert submit.arguments == {**DRAFT["submit"], REQUEST_ID: str(card.id)}
    note = rig.conversations.messages[card.conversation_id][-1].message
    assert note.role == "system" and note.content.startswith("Sent: Leave request LV-1")
    with pytest.raises(ActionUnavailable) as again:
        await rig.actions.confirm(employee(), card.id)
    assert again.value.reason == "sent"
    assert len([c for c in rig.tools.calls if c.call.name == "leave.submit"]) == 1


async def test_only_the_person_who_asked_may_confirm_or_cancel() -> None:
    rig = await rig_for({"leave.propose": ToolResult("", ok=True, data=DRAFT)})
    card = next(e for e in await propose(rig) if isinstance(e, ActionProposed)).proposal
    for act in (rig.actions.confirm, rig.actions.cancel):
        with pytest.raises(ActionUnavailable) as refused:
            await act(employee("E999"), card.id)
        assert refused.value.reason == "not_found"


async def test_a_draft_past_its_time_cannot_be_sent() -> None:
    rig = await rig_for({"leave.propose": ToolResult("", ok=True, data=DRAFT)})
    card = next(e for e in await propose(rig) if isinstance(e, ActionProposed)).proposal
    rig.actions.now = lambda: datetime.now(UTC) + timedelta(seconds=LEAVE.expires_s + 1)
    assert (await rig.actions.for_conversation(employee(), card.conversation_id))[
        0
    ].status == "expired"
    with pytest.raises(ActionUnavailable) as late:
        await rig.actions.confirm(employee(), card.id)
    assert late.value.reason == "expired"


async def test_a_system_that_does_not_answer_leaves_it_to_send_again() -> None:
    down = ToolResult("", ok=False, error="upstream_error")
    rig = await rig_for(
        {"leave.propose": ToolResult("", ok=True, data=DRAFT), "leave.submit": down}
    )
    card = next(e for e in await propose(rig) if isinstance(e, ActionProposed)).proposal

    waiting = await rig.actions.confirm(employee(), card.id)
    assert (waiting.status, waiting.outcome) == ("proposed", NOT_ANSWERED)

    rig.tools.results["leave.submit"] = ToolResult("", ok=True, data={"reference": "LV-2"})
    assert (await rig.actions.confirm(employee(), card.id)).reference == "LV-2"
    ids = {c.call.arguments[REQUEST_ID] for c in rig.tools.calls if c.call.name == "leave.submit"}
    assert ids == {str(card.id)}  # the same request both times: the system does it once


async def test_a_refused_send_ends_the_proposal() -> None:
    refused = ToolResult("", ok=False, error="denied")
    rig = await rig_for(
        {"leave.propose": ToolResult("", ok=True, data=DRAFT), "leave.submit": refused}
    )
    card = next(e for e in await propose(rig) if isinstance(e, ActionProposed)).proposal
    done = await rig.actions.confirm(employee(), card.id)
    assert done.status == "failed" and "not allowed" in done.outcome
    assert "action_failed" in rig.audit.names()


async def test_cancelling_discards_the_draft() -> None:
    rig = await rig_for({"leave.propose": ToolResult("", ok=True, data=DRAFT)})
    card = next(e for e in await propose(rig) if isinstance(e, ActionProposed)).proposal
    assert (await rig.actions.cancel(employee(), card.id)).status == "cancelled"
    with pytest.raises(ActionUnavailable):
        await rig.actions.confirm(employee(), card.id)


def test_a_draft_is_bounded_and_needs_arguments_to_submit() -> None:
    assert read_draft({"summary": "x"}) is None
    assert read_draft([1, 2]) is None
    many = {**DRAFT, "fields": [{"label": f"F{i}", "value": i} for i in range(50)]}
    draft = read_draft({**many, "summary": "y" * 1000})
    assert draft is not None and len(draft.fields) == 12 and len(draft.summary) == 300
    assert replace(draft, fields=()).submit == DRAFT["submit"]


async def test_a_pattern_for_another_kind_of_help_starts_it_mid_subject() -> None:
    """ "Book leave" while on the leave balance: the request feature's pattern says it is a new
    subject, in code; the model is not asked "about the balance, or something else?"."""
    balance = Feature(
        "my_leave", "record_lookup", "My leave", "Leave balance.", "Answer.", ("leave.balance",), ()
    )
    request = replace(MY_LEAVE, id="leave_request", route_patterns=(r"(?i)\bbook\b.*\bleave\b",))
    model = FakeModel(
        replies=[
            ModelReply(None, tool_calls=(ToolCall("1", "leave.balance", {}),)),
            ModelReply("You have 13 days left."),
            PROPOSE,
        ]
    )
    cited = (Citation("record", "Leave balance", "E100"),)
    rig = await make_rig(
        model,
        results={
            "leave.balance": ToolResult("", ok=True, data={"left": "13"}, citations=cited),
            "leave.propose": ToolResult("", ok=True, data=DRAFT),
        },
        specs=[
            spec("leave.balance", OPEN),
            spec("leave.propose", OPEN),
            spec("leave.submit", OPEN),
        ],
        features=(balance, request),
        default="my_leave",
        actions=(LEAVE,),
    )
    conversation = uuid4()
    await collect_events(rig.orchestrator.ask(employee(), conversation, "Leave left?", "my_leave"))
    events = await collect_events(
        rig.orchestrator.ask(employee(), conversation, "Please book leave from 9 to 13 Nov")
    )
    selected = [e.feature_id for e in events if isinstance(e, FeatureSelected)]
    assert selected == ["leave_request"]
    assert any(isinstance(e, ActionProposed) for e in events)


def test_a_pattern_wins_over_the_kind_of_help_just_picked() -> None:
    """Picked "my leave" (a subject opened, nothing asked yet), then typed "book leave": the
    request, not the balance's first question. A message naming a record is left to its own
    rules."""
    stack = ContextStack()
    stack.push("my_leave")
    book = certain(stack, "book leave", {}, None, None, patterned="leave_request")
    assert book == Reading("new", feature_id="leave_request", by="pattern")
    own = certain(stack, "book leave", {}, None, None, patterned="my_leave")
    assert own is not None and own.action == "continue"
