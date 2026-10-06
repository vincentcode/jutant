"""Playbook steps that look a record up with the reply, and choices the record answers."""

from dataclasses import replace
from typing import Any
from uuid import uuid4

from core.events import Completed, PlaybookStepShown, TextDelta, ToolStarted
from core.types import Citation, ModelReply, Playbook, PlaybookStep, StepLookup, ToolResult
from providers.llm.fake import FakeModel
from tests.builders import FEATURES, collect_events, make_rig, spec, teller

REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {"reference": {"type": "string"}},
    "required": ["reference"],
}
TRANSFERS = {
    "TX-0002": {
        "reference": "TX-0002",
        "status": "failed",
        "failure_code": "E51",
        "failure_reason": "Beneficiary account closed",
    },
    "TX-0003": {"reference": "TX-0003", "status": "reversed"},
    "TX-0009": {"reference": "TX-0009", "status": "failed", "branch": "KSI-02"},
}
FAILED_TRANSFER = Playbook(
    "failed_transfer",
    "Failed transfer",
    "A transfer failed.",
    (
        PlaybookStep(
            1,
            "Get the reference",
            "Enter the reference.",
            ("staff",),
            "text",
            lookup=StepLookup("transactions.get_status", "reference", r"(?i)\b(TX-\d+)\b"),
        ),
        PlaybookStep(
            2,
            "Check the status",
            "Which status does {1.reference} show?",
            ("staff",),
            "choice",
            ("failed", "pending", "completed"),
            {"failed": 3, "pending": 4, "completed": 4},
            answer_from="1.status",
        ),
        PlaybookStep(
            3,
            "Explain",
            "Failed: {1.failure_reason} (code {1.failure_code}).",
            ("staff",),
            next_on={"confirm": 5},
        ),
        PlaybookStep(4, "Advise", "Pending or completed.", ("staff",), next_on={"confirm": 5}),
        PlaybookStep(5, "Close", "Confirm the outcome.", ("staff",), "none"),
    ),
)


def status(arguments: dict[str, Any]) -> ToolResult:
    record = TRANSFERS.get(arguments["reference"].upper())  # as the real tool does
    if record is None:
        return ToolResult("", ok=False, error="not_found")
    if record.get("branch") == "KSI-02":
        return ToolResult("", ok=False, error="denied")
    return ToolResult(
        "",
        ok=True,
        data=record,
        citations=(Citation("record", "Transaction", record["reference"]),),
    )


async def started_run():
    features = tuple(
        replace(f, tools=("transactions.get_status",)) if f.id == "troubleshooting" else f
        for f in FEATURES
    )
    rig = await make_rig(
        FakeModel(replies=[ModelReply("failed_transfer")]),
        results={"transactions.get_status": status},
        specs=[spec("transactions.get_status", REFERENCE_SCHEMA)],
        features=features,
        playbooks=[FAILED_TRANSFER],
    )
    conversation = uuid4()
    await collect_events(
        rig.orchestrator.ask(teller(), conversation, "a transfer failed", "troubleshooting")
    )
    return rig, conversation


def shown(events) -> list[PlaybookStep]:
    return [e.step for e in events if isinstance(e, PlaybookStepShown)]


async def test_the_reference_is_looked_up_and_its_status_picks_the_branch() -> None:
    rig, conversation = await started_run()

    events = await collect_events(
        rig.orchestrator.ask(teller(), conversation, "the reference is tx-0002")
    )

    [call] = [e.call for e in events if isinstance(e, ToolStarted)]
    assert (call.name, call.arguments) == ("transactions.get_status", {"reference": "tx-0002"})
    assert any(
        "Check the status: failed (from the record)." in e.text
        for e in events
        if isinstance(e, TextDelta)
    )
    [step] = shown(events)
    assert step.order == 3  # the failed branch, without asking
    assert step.instruction == "Failed: Beneficiary account closed (code E51)."
    answer = events[-1].answer
    assert isinstance(events[-1], Completed)
    assert answer.citations == (Citation("record", "Transaction", "TX-0002"),)
    assert "tool_called" in [kind for _, kind, _ in rig.audit.events]  # through the gateway


async def test_the_record_stays_with_the_run_for_later_steps() -> None:
    rig, conversation = await started_run()
    await collect_events(rig.orchestrator.ask(teller(), conversation, "TX-0002"))
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "cancel? no"))
    # an unclear reply re-shows the step, still filled from the stored record
    assert shown(events)[0].instruction == "Failed: Beneficiary account closed (code E51)."


async def test_a_reply_without_a_reference_is_asked_again() -> None:
    rig, conversation = await started_run()
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "12345678"))
    assert not any(isinstance(e, ToolStarted) for e in events)
    assert "could not find a reference" in "".join(
        e.text for e in events if isinstance(e, TextDelta)
    )
    assert shown(events)[0].order == 1


async def test_an_unknown_reference_keeps_the_run_on_the_step() -> None:
    rig, conversation = await started_run()
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "TX-0404"))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "No record was found for TX-0404" in text
    assert shown(events)[0].order == 1


async def test_a_refused_record_keeps_the_run_on_the_step_and_shows_nothing() -> None:
    rig, conversation = await started_run()
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "TX-0009"))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "You don't have access to TX-0009" in text
    assert shown(events)[0].order == 1


async def test_a_status_that_is_no_choice_is_asked() -> None:
    rig, conversation = await started_run()
    events = await collect_events(rig.orchestrator.ask(teller(), conversation, "TX-0003"))
    [step] = shown(events)
    assert step.order == 2 and step.instruction == "Which status does TX-0003 show?"
