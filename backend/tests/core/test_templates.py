from uuid import uuid4

from core.documents.chunking import split
from core.events import PlaybookStepShown, TextDelta
from core.extraction.extractor import extract, parse_json_object
from core.types import ModelReply, Playbook, PlaybookStep, ToolCall, ToolResult
from providers.llm.fake import FakeModel
from tests.builders import BLOCKED_CARD, collect_events, final_answer, make_rig, teller

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
