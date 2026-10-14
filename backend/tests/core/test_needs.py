"""What a feature needs before it looks anything up: read from messages, kept with the subject,
and asked for in code when missing."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.context.stack import ContextStack
from core.evals.turns import render, summarise
from core.events import Clarify, Completed, TextDelta
from core.features.needs import ASKED, WAY, given, missing, read_date, read_period, update
from core.packs.contract import _needs_problems
from core.packs.manifest import DetailDef, FeatureDef
from core.types import ArgumentSource, Detail, EntityType, ModelReply, Needs, Prefetch
from providers.llm.fake import FakeModel
from tests.builders import FEATURES, collect_events, make_rig, record_result, spec, teller

TODAY = date(2026, 10, 12)
SYSTEM = Detail(
    "system",
    "the system",
    choose=(("app", "Mobile app"), ("short_code", "Short code"), ("unsure", "Not sure")),
    words=(("app", ("the app",)),),
    ask="Which system was it made on?",
)
DETAILS = (
    SYSTEM,
    Detail("reference", "the reference", entity="ref", title="Transaction reference"),
    Detail("phone", "the phone number", entity="phone"),
    Detail("account", "the account number", entity="acct"),
    Detail("day", "the date", date=True),
)
NEEDS = Needs(
    first=("system",),
    one_of=(("phone", "day"), ("account", "day")),
    by="system",
    one_of_by=(("short_code", (("reference",), ("phone", "day"))),),
)
# A phone number and an account number look the same: ten digits.
TYPES = (
    EntityType("ref", r"\bR-\d+\b"),
    EntityType("phone", r"\b0\d{9}\b"),
    EntityType("acct", r"\b\d{10}\b"),
)
NUMBER = {"phone": "0244123456", "acct": "0244123456"}
FIND = Prefetch(
    "records.find",
    {
        "system": ArgumentSource(detail="system"),
        "reference": ArgumentSource(detail="reference", optional=True),
        "phone": ArgumentSource(detail="phone", optional=True),
        "account": ArgumentSource(detail="account", optional=True),
        "day": ArgumentSource(detail="day", optional=True),
    },
)
FEATURE = replace(
    FEATURES[1], tools=("records.find",), prefetch=(FIND,), details=DETAILS, needs=NEEDS
)
FIND_SCHEMA = {
    "type": "object",
    "properties": {
        k: {"type": "string"} for k in ("system", "reference", "phone", "account", "day")
    },
    "required": ["system"],
}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("it was on 2026-10-03", "2026-10-03"),
        ("on 03/10/2026", "2026-10-03"),
        ("3rd October", "2026-10-03"),
        ("Oct 3, 2025", "2025-10-03"),
        ("made yesterday", "2026-10-11"),
        ("today please", "2026-10-12"),
        ("on 20 December", "2025-12-20"),  # no year: the latest one not after today
        ("31/02/2026", None),
        ("no date here, 0244123456", None),
    ],
)
def test_dates_are_read_in_code(text: str, expected: str | None) -> None:
    assert read_date(text, TODAY) == expected


def test_a_message_gives_details_by_pattern_name_and_date() -> None:
    found = given(FEATURE, "on the app, 0244123456, yesterday", {"phone": "0244123456"}, TODAY)
    assert found == {"system": "app", "phone": "0244123456", "day": "2026-10-11"}


@pytest.mark.parametrize("text", ["something went wrong", "the app or the short code?"])
def test_a_choice_is_never_guessed(text: str) -> None:
    assert "system" not in given(FEATURE, text, {}, TODAY)  # none named, or two


def test_the_choice_asked_first_comes_with_its_values() -> None:
    wanted = missing(FEATURE, {"reference": "R-1"})
    assert wanted is not None
    assert wanted.question == "Which system was it made on?"
    assert [title for _, title in wanted.choices] == ["Mobile app", "Short code", "Not sure"]


def test_with_several_ways_staff_choose_how_to_find_it_first() -> None:
    assert missing(FEATURE, {"system": "short_code", "reference": "R-1"}) is None
    wanted = missing(FEATURE, {"system": "short_code"})
    assert wanted is not None and wanted.question == "How would you like to find it?"
    assert wanted.choices == (
        ("reference", "Transaction reference"),
        ("phone+day", "Phone number and date"),
    )
    chosen = update(
        FEATURE, {"system": "short_code", ASKED: wanted.asked}, "Phone number and date", {}
    )
    assert chosen[WAY] == "phone+day"
    asked = missing(FEATURE, chosen)
    assert (
        asked is not None
        and asked.question == "To look this up I need the phone number and the date."
    )


def test_a_number_typed_after_the_way_was_chosen_is_what_was_asked_for() -> None:
    known = {"system": "app", WAY: "account+day", ASKED: "values"}
    got = update(FEATURE, known, "0244123456, yesterday", NUMBER, TODAY)
    assert (got.get("account"), "phone" in got) == ("0244123456", False)
    assert missing(FEATURE, got) is None


def test_a_number_that_could_be_either_is_asked_about_not_guessed() -> None:
    got = update(FEATURE, {"system": "app"}, "0244123456, yesterday", NUMBER, TODAY)
    wanted = missing(FEATURE, got)
    assert wanted is not None
    assert wanted.question == "Is 0244123456 the phone number or the account number?"
    assert [t for _, t in wanted.choices] == ["Phone number", "Account number"]
    answered = update(FEATURE, {**got, ASKED: wanted.asked}, "Account number", {}, TODAY)
    assert ("account" in answered, "phone" in answered) == (True, False)
    assert missing(FEATURE, answered) is None


def test_the_system_named_can_settle_which_a_number_is() -> None:
    got = update(FEATURE, {"system": "short_code"}, "0244123456 yesterday", NUMBER, TODAY)
    assert ("phone" in got, "account" in got) == (True, False)  # not searched by account there
    assert missing(FEATURE, got) is None


def test_once_a_set_is_started_only_its_missing_part_is_asked() -> None:
    wanted = missing(FEATURE, {"system": "short_code", "phone": "0244123456"})
    assert wanted is not None
    assert wanted.question == "To look this up I need the date."


async def rig_for(model: FakeModel):
    return await make_rig(
        model,
        results={"records.find": record_result("Record", "R-9", {"status": "failed"})},
        specs=[spec("records.find", FIND_SCHEMA), *(spec(t) for f in FEATURES for t in f.tools)],
        features=(FEATURES[0], FEATURE, *FEATURES[2:]),
        entity_types=TYPES,
    )


async def test_asked_in_code_until_enough_then_looked_up() -> None:
    rig = await rig_for(FakeModel(replies=[ModelReply("status"), ModelReply("It failed.")]))
    conversation = uuid4()
    ask = rig.orchestrator.ask

    first = await collect_events(ask(teller(), conversation, "a transfer went missing", FEATURE.id))
    [buttons] = [e for e in first if isinstance(e, Clarify)]
    assert (buttons.reason, buttons.choices[1].title, buttons.choices[1].kind) == (
        "detail",
        "Short code",
        "detail",
    )
    assert rig.tools.calls == [] and rig.model.calls == []  # no model, no lookup

    second = await collect_events(ask(teller(), conversation, "Short code", reply_as="detail"))
    [ways] = [e for e in second if isinstance(e, Clarify)]
    assert [c.title for c in ways.choices] == ["Transaction reference", "Phone number and date"]

    way = await collect_events(
        ask(teller(), conversation, "Phone number and date", reply_as="detail")
    )
    assert [e.text for e in way if isinstance(e, TextDelta)] == [
        "To look this up I need the phone number and the date."
    ]

    # Names a new entity, but answers what was asked: the same subject, not a new one.
    third = await collect_events(ask(teller(), conversation, "0244123456, on 3 October"))
    assert rig.tools.calls[0].call.arguments == {
        "system": "short_code",
        "phone": "0244123456",
        "day": "2026-10-03",
    }
    assert isinstance(third[-1], Completed) and third[-1].answer.text == "It failed."
    reads = [d for _, name, d in rig.audit.events if name == "turn_read"]
    assert [r["by"] for r in reads] == ["first", "staff", "staff", "detail"]
    assert {(r["action"], r["frame"]) for r in reads[1:]} == {("continue", 1)}


async def test_a_value_named_in_the_message_is_not_asked_for() -> None:
    rig = await rig_for(FakeModel(replies=[ModelReply("status"), ModelReply("It failed.")]))
    await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "R-9 on the short code", FEATURE.id)
    )
    assert rig.tools.calls[0].call.arguments == {"system": "short_code", "reference": "R-9"}


async def test_starting_the_kind_of_help_asks_its_first_need() -> None:
    rig = await rig_for(FakeModel())
    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), FEATURE.title, FEATURE.id, reply_as="start")
    )
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Which system was it made on?"]
    assert any(isinstance(e, Clarify) and e.reason == "detail" for e in events)


def test_a_detail_is_found_one_way_only() -> None:
    with pytest.raises(ValidationError):
        DetailDef(label="x", entity="ref", date=True)
    with pytest.raises(ValidationError):
        DetailDef(label="x", choose={"a": "A"}, words={"b": ["bee"]})


def test_the_contract_checks_what_needs_name() -> None:
    feature = FeatureDef.model_validate(
        {
            "id": "f",
            "template": "record_lookup",
            "title": "F",
            "description": "F",
            "prompt": "p.md",
            "details": {
                "system": {"label": "the system", "choose": {"app": "App"}},
                "phone": {"label": "the phone", "entity": "mobile"},
            },
            "needs": {"first": ["system"], "by": "system", "one_of_by": {"ussd": [["day"]]}},
        }
    )
    assert _needs_problems(feature, {"phone"}) == [
        "feature f: detail phone: unknown entity mobile",
        "feature f: needs names unknown detail day",
        "feature f: needs.one_of_by: ussd is not a value of system",
        "feature f: needs details that no prefetch call uses",
    ]


def test_details_and_awaiting_are_kept_between_turns() -> None:
    stack = ContextStack()
    frame = stack.push("f")
    stack.put(replace(frame, details={"system": "app"}, awaiting=True))
    kept = ContextStack.from_dict(stack.as_dict()).top
    assert kept is not None and (kept.details, kept.awaiting) == ({"system": "app"}, True)


def test_asking_for_a_value_is_not_counted_as_asking_what_a_message_is() -> None:
    report = summarise(
        [
            ("c", "question_asked", {"text": "a transfer went missing"}),
            ("c", "clarify_shown", {"reason": "detail", "choices": [{"kind": "detail"}]}),
            ("c", "question_asked", {"text": "Short code", "reply_as": "detail", "picked": 0}),
        ]
    )
    assert (report.turns, report.asked_total, report.asked["detail"]) == (2, 0, 1)
    assert "values asked for    1" in render(report)


@pytest.mark.parametrize(
    ("text", "period"),
    [
        ("10 to 14 November", "2026-11-10/2026-11-14"),
        ("I'd like 10-14 Nov off", "2026-11-10/2026-11-14"),
        ("Nov 10-14", "2026-11-10/2026-11-14"),
        ("from 10 Nov to 2 Dec", "2026-11-10/2026-12-02"),
        ("just 12 Nov", "2026-11-12/2026-11-12"),
        ("28 Dec to 3 Jan", "2026-12-28/2027-01-03"),
        ("10/11/2026 - 14/11/2026", "2026-11-10/2026-11-14"),
        ("5 to 9 Oct", "2026-10-05/2026-10-09"),  # last week: sick leave, recorded after
        ("20 Jan", "2027-01-20/2027-01-20"),  # nearest: next January, not last
        ("14 Nov to 10 Nov", None),  # an end before the start is refused, never moved a year on
        ("annual leave", None),
    ],
)
def test_a_period_is_read_in_code(text: str, period: str | None) -> None:
    assert read_period(text, date(2026, 10, 13), nearest=True) == period


def test_a_date_without_a_year_is_the_latest_past_one_unless_nearest() -> None:
    today = date(2026, 10, 13)
    assert read_date("20 Oct", today) == "2025-10-20"  # a transaction: it happened before
    assert read_date("20 Oct", today, nearest=True) == "2026-10-20"
    assert read_date("tomorrow", today) == "2026-10-14"
