from dataclasses import replace
from typing import Any
from uuid import uuid4

from core.documents.chunking import split
from core.documents.summarise import split_into_parts, summarise
from core.events import PlaybookStepShown, TextDelta
from core.extraction.extractor import extract, parse_json_object
from core.types import (
    Citation,
    ModelReply,
    Playbook,
    PlaybookStep,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from providers.llm.fake import FakeModel
from tests.builders import (
    BLOCKED_CARD,
    FEATURES,
    collect_events,
    final_answer,
    make_rig,
    teller,
)

SCHEMAS = {
    "id_card": ["full_name", "id_number", "expiry_date"],
    "payslip": ["employer", "net_pay"],
}
DORMANT = Playbook(
    "dormant_account",
    "Dormant account",
    "Reactivate a dormant account.",
    (PlaybookStep(1, "Verify", "Verify the customer.", ("staff",)),),
)


# --- document_extraction ------------------------------------------------------


async def test_extraction_uses_the_schema_the_question_names() -> None:
    reply = ModelReply(
        '```json\n{"full_name": "Ama Mensah", "id_number": "GHA-123", '
        '"expiry_date": "", "extra": "ignored"}\n```'
    )
    rig = await make_rig(FakeModel(replies=[reply]), extraction_schemas=SCHEMAS)

    answer = await final_answer(
        rig.orchestrator.ask(
            teller(), uuid4(), "Extract the ID card fields", "extraction", upload_text="ID CARD ..."
        )
    )

    assert "- Full name: Ama Mensah" in answer.text
    assert "- Expiry date: not found" in answer.text
    assert "extra" not in answer.text
    assert "full_name, id_number, expiry_date" in rig.model.calls[0].messages[0].content


async def test_extraction_asks_the_model_for_the_document_type_when_unnamed() -> None:
    model = FakeModel(
        replies=[ModelReply("payslip"), ModelReply('{"employer": "Acme", "net_pay": "900"}')]
    )
    rig = await make_rig(model, extraction_schemas=SCHEMAS)

    answer = await final_answer(
        rig.orchestrator.ask(
            teller(),
            uuid4(),
            "Pull the details from this",
            "extraction",
            upload_text="ACME LTD PAYSLIP",
        )
    )

    assert "- Employer: Acme" in answer.text


async def test_upload_without_a_field_request_is_summarised() -> None:
    rig = await make_rig(
        FakeModel(replies=[ModelReply("A circular about fees.")]), extraction_schemas=SCHEMAS
    )

    answer = await final_answer(
        rig.orchestrator.ask(
            teller(),
            uuid4(),
            "What is this about?",
            "extraction",
            upload_text="Fees change in May.",
        )
    )

    assert answer.text == "A circular about fees."


async def test_extraction_without_upload_uses_the_tool_loop() -> None:
    call = ToolCall("1", "documents.get", {"query": "circular 12"})
    model = FakeModel(replies=[ModelReply(None, (call,)), ModelReply("Summary.")])
    rig = await make_rig(
        model, results={"documents.get": ToolResult("", ok=True, data={"text": "..."})}
    )

    answer = await final_answer(
        rig.orchestrator.ask(teller(), uuid4(), "Summarise circular 12", "extraction")
    )

    assert answer.text == "Summary."
    assert rig.tools.calls[0].call.name == "documents.get"


SUMMARY = replace(FEATURES[4], id="summary", tools=("documents.search", "documents.get"))
DOC_ID = "6f1c2c1e-0000-0000-0000-000000000001"


OPEN_SPECS = [ToolSpec(n, n, {"type": "object"}) for n in ("documents.search", "documents.get")]


def documents(parts: list[str], hits: bool = True) -> dict[str, Any]:
    """Fake documents tools: a search that finds one document, and `get` serving its parts."""
    found = [{"document_id": DOC_ID, "title": "Circular 14", "section": "Purpose", "text": "x"}]
    search = ToolResult(
        "",
        ok=True,
        data=found if hits else [],
        citations=(Citation("document", "Circular 14", "Purpose"),),
    )

    def get(arguments: dict[str, Any]) -> ToolResult:
        n = arguments["part"]
        return ToolResult(
            "",
            ok=True,
            data={
                "document_id": DOC_ID,
                "title": "Circular 14",
                "text": parts[n - 1],
                "part": n,
                "parts": len(parts),
            },
            citations=(Citation("document", "Circular 14", "whole document"),),
        )

    return {"documents.search": search, "documents.get": get}


async def test_an_indexed_document_is_found_and_read_whole_in_code() -> None:
    model = FakeModel(replies=[ModelReply("- Tellers may reactivate.\n- From 1 November.")])
    rig = await make_rig(
        model, results=documents(["Part one. ", "Part two."]), features=(SUMMARY,), specs=OPEN_SPECS
    )

    answer = await final_answer(
        rig.orchestrator.ask(teller(), uuid4(), "Summarise circular 14", "summary")
    )

    calls = [(c.call.name, c.call.arguments) for c in rig.tools.calls]
    assert calls == [
        ("documents.search", {"query": "Summarise circular 14"}),
        ("documents.get", {"document_id": DOC_ID, "part": 1}),
        ("documents.get", {"document_id": DOC_ID, "part": 2}),
    ]
    assert len(model.calls) == 1  # a short document is summarised in one call
    assert "Part one. Part two." in model.calls[0].messages[1].content
    assert answer.text == "Summary of Circular 14:\n\n- Tellers may reactivate.\n- From 1 November."
    assert Citation("document", "Circular 14", "whole document") in answer.citations


async def test_no_matching_document_is_said_plainly_without_the_model() -> None:
    model = FakeModel()
    rig = await make_rig(
        model, results=documents([], hits=False), features=(SUMMARY,), specs=OPEN_SPECS
    )
    answer = await final_answer(rig.orchestrator.ask(teller(), uuid4(), "Summarise X", "summary"))
    assert answer.text.startswith("I could not find a document") and model.calls == []


async def test_a_very_long_document_is_read_up_to_a_limit_and_says_so() -> None:
    parts = [f"Part {n}. " for n in range(1, 11)]
    model = FakeModel(replies=[ModelReply("Summary.")])
    rig = await make_rig(model, results=documents(parts), features=(SUMMARY,), specs=OPEN_SPECS)
    answer = await final_answer(rig.orchestrator.ask(teller(), uuid4(), "Summarise it", "summary"))
    assert len(rig.tools.calls) == 1 + 8
    assert answer.text.endswith(
        "This covers the first 8 of 10 parts of the document; open it for the rest."
    )


async def test_a_long_text_is_summarised_in_parts_then_combined() -> None:
    section = " ".join(["word"] * 1500)
    text = f"# One\n\n{section}\n\n# Two\n\n{section}"
    assert len(split_into_parts(text)) == 2
    model = FakeModel(replies=[ModelReply("First."), ModelReply("Second."), ModelReply("Whole.")])
    assert await summarise(model, text) == "Whole."
    assert model.calls[2].messages[1].content == "First.\n\nSecond."


async def test_extractor_never_guesses_on_an_unparseable_reply() -> None:
    values = await extract(
        FakeModel(replies=[ModelReply("Sorry, I can't read it.")]), "x", ["a", "b"]
    )
    assert values == {"a": None, "b": None}


def test_parse_json_object_tolerates_surrounding_text() -> None:
    assert parse_json_object('Here you go: {"a": 1} hope it helps') == {"a": 1}
    assert parse_json_object("[1, 2]") == {}
    assert parse_json_object("{broken") == {}


# --- guided_playbook ----------------------------------------------------------


async def test_model_chooses_between_playbooks() -> None:
    rig = await make_rig(
        FakeModel(replies=[ModelReply("dormant_account")]), playbooks=[BLOCKED_CARD, DORMANT]
    )

    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "account not used for years", "troubleshooting")
    )

    step = next(e for e in events if isinstance(e, PlaybookStepShown))
    assert step.playbook_id == "dormant_account"


async def test_unmatched_problem_lists_the_playbooks() -> None:
    rig = await make_rig(
        FakeModel(replies=[ModelReply("not sure")]), playbooks=[BLOCKED_CARD, DORMANT]
    )

    events = await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "help", "troubleshooting")
    )

    text = next(e.text for e in events if isinstance(e, TextDelta))
    assert "Blocked card" in text and "Dormant account" in text


# --- chunking -----------------------------------------------------------------


def test_chunks_keep_their_section_heading() -> None:
    text = "# KYC Policy\n\nIntro.\n\n4.2 Joint accounts\n\nBoth holders must provide ID.\n"
    chunks = split(text)
    assert [(c.section, c.text) for c in chunks] == [
        ("KYC Policy", "Intro."),
        ("4.2 Joint accounts", "Both holders must provide ID."),
    ]


def test_long_text_is_split_with_overlap() -> None:
    words = [f"w{i}" for i in range(100)]
    chunks = split(" ".join(words), max_tokens=40, overlap=8)  # 30 words, 6 overlapping
    assert all(len(c.text.split()) <= 30 for c in chunks)
    assert chunks[1].text.split()[:6] == chunks[0].text.split()[-6:]
    assert chunks[-1].text.split()[-1] == "w99"


def test_numbered_list_items_are_not_headings() -> None:
    chunks = split("1. Bring your ID.\n2. Sign the form.")
    assert chunks[0].section == ""
