"""One full chat turn per banking feature, through the API as deployed: FastAPI, the Django
stores on PostgreSQL, the real MCP servers in-process on the fake bank, and a scripted model.

Each test asks as staff would, and checks what they would see (the answer and its sources),
what the model was given, and what the audit log recorded.
"""

from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command

from api.tests.conftest import api, make_staff
from apps.audit.models import AuditEvent
from apps.knowledge.tests.factories import indexed_document, vector
from core.orchestrator.orchestrator import NO_SOURCE_MESSAGE
from core.types import ModelReply, ToolCall

pytestmark = pytest.mark.django_db(transaction=True)


def calls(name: str, **arguments: Any) -> ModelReply:
    return ModelReply(None, (ToolCall(f"call-{name}", name, arguments),))


def answer(events: list[tuple[str, Any]]) -> dict[str, Any]:
    name, data = events[-1]
    assert name == "completed", events
    return data["answer"]


def tools_used(events: list[tuple[str, Any]]) -> list[str]:
    return [data["call"]["name"] for name, data in events if name == "tool_started"]


async def audit_events() -> list[str]:
    return await sync_to_async(lambda: list(AuditEvent.objects.values_list("event", flat=True)))()


async def index(title: str, section: str, text: str, classification: str = "internal") -> None:
    await sync_to_async(indexed_document)(
        title, [(section, text, vector(0))], classification=classification
    )


async def test_policy_qa_answers_from_the_policy_and_cites_it() -> None:
    await make_staff("ama")
    await index(
        "KYC Policy", "4.2 Joint accounts", "Both holders of a joint account must provide ID."
    )
    turn = [
        ModelReply("policy_qa"),  # the router's choice: no feature was picked
        # no search call scripted: policy questions are searched in code before the model
        ModelReply("Both holders must provide ID (KYC Policy, 4.2)."),
    ]
    async with api(*turn) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(), text="What ID do joint holders need?"
        )
        router_call = client.model.calls[0]

    assert router_call.tools == []  # routing never sees tools
    result = answer(events)
    assert tools_used(events) == ["documents.search"]
    assert result["feature_id"] == "policy_qa"
    assert result["citations"] == [
        {"kind": "document", "title": "KYC Policy", "locator": "4.2 Joint accounts"}
    ]
    assert await audit_events() == [
        "question_asked",
        "turn_read",
        "feature_routed",
        "tool_called",
        "answer_returned",
    ]


async def test_policy_qa_finds_nothing_and_says_so() -> None:
    await make_staff("ama")
    turn = [calls("documents.search", query="pet insurance"), ModelReply("Pets are covered.")]
    async with api(*turn) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(), text="Are pets covered?", feature_id="policy_qa"
        )
    assert answer(events)["text"] == NO_SOURCE_MESSAGE  # never an uncited policy answer


async def test_internal_documents_stay_hidden_from_roles_without_the_label() -> None:
    """The banking pack labels documents public or internal; every staff role may read both,
    so this checks the label filter with a label no role holds."""
    await make_staff("ama")
    await index("Board minutes", "1 Pay", "Joint holders salary review.", classification="board")
    turn = [calls("documents.search", query="joint holders"), ModelReply("Nothing found.")]
    async with api(*turn) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(), text="joint holders?", feature_id="policy_qa"
        )
    finished = next(data for name, data in events if name == "tool_finished")
    assert finished["result"]["citations"] == []
    assert answer(events)["text"] == NO_SOURCE_MESSAGE


async def test_product_lookup_searches_then_reads_the_product() -> None:
    await make_staff("ama")
    turn = [
        calls("services.search_products", query="savings"),
        calls("services.get_product", product_code="SAV-STD"),
        ModelReply("Standard Savings pays 8.5% with no monthly fee."),
    ]
    async with api(*turn) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(), text="Rate on savings?", feature_id="product_lookup"
        )
    assert tools_used(events) == ["services.search_products", "services.get_product"]
    assert {"kind": "record", "title": "Product", "locator": "SAV-STD"} in answer(events)[
        "citations"
    ]


async def test_transaction_lookup_explains_a_failed_transfer() -> None:
    await make_staff("ama")
    turn = [
        calls("transactions.get_status", reference="TX-0002"),
        ModelReply("TX-0002 failed (E51): beneficiary account closed."),
    ]
    async with api(*turn) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(),
            text="Why did TX-0002 fail?",
            feature_id="transaction_lookup",
        )
    assert answer(events)["citations"] == [
        {"kind": "record", "title": "Transaction", "locator": "TX-0002"}
    ]


async def test_transaction_lookup_refuses_another_branch() -> None:
    await make_staff("kojo", branch="KSI-02")
    async with api() as client:  # no model replies: a refusal never reaches the model
        await client.login("kojo")
        events = await client.ask(
            await client.conversation(),
            text="Activity on 0011223344",
            feature_id="transaction_lookup",
        )
        assert client.model.calls == []
    finished = next(data for name, data in events if name == "tool_finished")
    assert finished["result"]["error"] == "denied"
    assert events[-1] == ("failed", {"reason": "denied"})  # shown as "no access", at once
    assert "tool_denied" in await audit_events()


async def test_code_explainer_looks_up_the_code() -> None:
    await make_staff("ama")
    await index(
        "Error codes", "E51", "E51 means the beneficiary account is closed. Contact the customer."
    )
    turn = [
        calls("documents.search", query="E51"),
        ModelReply("Meaning: beneficiary account closed."),
    ]
    async with api(*turn) as client:
        await client.login("ama")
        events = await client.ask(
            await client.conversation(), text="What is E51?", feature_id="code_explainer"
        )
    assert answer(events)["citations"] == [
        {"kind": "document", "title": "Error codes", "locator": "E51"}
    ]


async def test_form_guidance_lists_what_a_request_needs() -> None:
    await make_staff("efua", role="customer_service")
    turn = [
        calls("services.get_requirements", request_type="joint account opening"),
        ModelReply("- Account opening form\n- Joint mandate form\n- All holders sign"),
    ]
    async with api(*turn) as client:
        await client.login("efua")
        events = await client.ask(
            await client.conversation(), text="Joint account opening?", feature_id="form_guidance"
        )
    assert answer(events)["citations"] == [
        {"kind": "record", "title": "Requirements", "locator": "joint_account_opening"}
    ]


async def test_troubleshooting_walks_a_playbook_to_the_end() -> None:
    await make_staff("ama")
    await sync_to_async(call_command)("load_pack_playbooks")
    async with api(ModelReply("blocked_card")) as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        steps = []
        for text in ("Card is blocked", "done", "expired", "done"):
            # After the first, answers clicked on the step card: not read by the model.
            reply_as = None if text == "Card is blocked" else "answer"
            events = await client.ask(
                conversation_id, text=text, feature_id="troubleshooting", reply_as=reply_as
            )
            steps += [data["step"]["order"] for name, data in events if name == "playbook_step"]
        last = answer(events)

    assert steps == [1, 2, 5, 7]  # expired -> order a replacement -> close
    assert last["text"] == "Procedure complete."


async def test_document_summary_extraction_summarises_an_upload() -> None:
    await make_staff("ama")
    async with api(ModelReply("A notice about an ID card.")) as client:
        await client.login("ama")
        conversation_id = await client.conversation()
        upload = (
            await client.http.post(
                f"/api/conversations/{conversation_id}/upload",
                files={"file": ("notice.txt", b"Circular 12: fees change in May.", "text/plain")},
            )
        ).json()
        events = await client.ask(
            conversation_id,
            text="What is this about?",
            feature_id="document_summary_extraction",
            upload_id=upload["upload_id"],
        )
    assert answer(events)["text"] == "A notice about an ID card."
    assert "document_uploaded" in await audit_events()


async def test_customer_360_for_customer_service_with_figures_from_code() -> None:
    await make_staff("efua", role="customer_service")
    turn = [
        calls("services.customer_summary", customer_number="C1001"),
        ModelReply("Ama Mensah: two accounts, GHS 6,021.25 in total."),
    ]
    async with api(*turn) as client:
        await client.login("efua")
        events = await client.ask(
            await client.conversation(), text="Summary of C1001", feature_id="customer_360"
        )
        tool_message = client.model.calls[1].messages[-1].content
    assert answer(events)["citations"] == [
        {"kind": "record", "title": "Customer", "locator": "C1001"}
    ]
    assert '"total_balance":{"GHS":"6021.25"}' in tool_message


async def test_every_banking_feature_is_covered_here() -> None:
    from django.conf import settings

    from core.packs.loader import load_pack

    covered = {
        "policy_qa",
        "product_lookup",
        "transaction_lookup",
        "code_explainer",
        "form_guidance",
        "troubleshooting",
        "document_summary_extraction",
        "customer_360",
    }
    assert {f.id for f in load_pack(settings.JUTANT_PACK_PATH).features} == covered


async def test_personal_data_is_masked_in_the_audit_log() -> None:
    await make_staff("ama")
    turn = [
        calls("transactions.list", account_number="0011223344"),
        ModelReply("Three transactions."),
    ]
    async with api(*turn) as client:
        await client.login("ama")
        await client.ask(
            await client.conversation(),
            text="Activity on 0011223344 for ama@example.com",
            feature_id="transaction_lookup",
        )
    details = await sync_to_async(
        lambda: list(AuditEvent.objects.values_list("detail", flat=True))
    )()
    logged = str(details)
    assert "0011223344" not in logged and "ama@example.com" not in logged
    assert "******3344" in logged
