"""The core orchestrator running on the real Django stores, with a fake model and fake tools.

Checks that the adapters behave the way the core expects: history, citations, playbook runs
and the audit trail all survive a round trip through PostgreSQL.
"""

from uuid import UUID

import pytest
from asgiref.sync import sync_to_async

from apps.audit import selectors as audit_selectors
from apps.audit.adapters import DjangoAuditSink
from apps.conversation import selectors as conversation_selectors
from apps.conversation.adapters import DjangoConversationStore, to_citations
from apps.playbooks import services as playbook_services
from apps.playbooks.adapters import DjangoPlaybookStore
from core.events import PlaybookStepShown
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.orchestrator.orchestrator import Orchestrator
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from core.types import Citation, ModelReply, ToolCall
from providers.llm.fake import FakeModel
from providers.mcp.fake import FakeToolClient
from tests.builders import BLOCKED_CARD, FEATURES, collect_events, doc_result, spec, teller

pytestmark = pytest.mark.django_db(transaction=True)


async def make_orchestrator(model: FakeModel, tools: FakeToolClient) -> Orchestrator:
    audit = DjangoAuditSink()
    registry = FeatureRegistry(FEATURES)
    orchestrator = Orchestrator(
        model=model,
        tools=tools,
        conversations=DjangoConversationStore(),
        playbooks=DjangoPlaybookStore(),
        audit=audit,
        registry=registry,
        router=FeatureRouter(model, registry, default="policy_qa"),
        gateway=ToolGateway(tools, ToolCatalog(tools), audit),
    )
    await orchestrator.load_tools()
    return orchestrator


async def start_conversation() -> UUID:
    return await DjangoConversationStore().create(teller())


async def test_document_answer_is_stored_with_citations_and_audited() -> None:
    model = FakeModel(
        replies=[
            ModelReply(None, (ToolCall("1", "documents.search", {"query": "kyc"}),)),
            ModelReply("Both holders must provide ID."),
        ]
    )
    tools = FakeToolClient(
        results={"documents.search": doc_result("KYC Policy", "4.2")},
        specs=[spec("documents.search")],
    )
    orchestrator = await make_orchestrator(model, tools)
    conversation_id = await start_conversation()

    await collect_events(
        orchestrator.ask(teller(), conversation_id, "KYC for 0011223344?", "policy_qa")
    )

    rows = await sync_to_async(conversation_selectors.messages)(conversation_id=conversation_id)
    assert [r.role for r in rows] == ["user", "assistant"]
    assert to_citations(rows[1]) == (Citation("document", "KYC Policy", "4.2"),)
    events = await sync_to_async(audit_selectors.events_for_conversation)(
        conversation_id=conversation_id
    )
    assert [e.event for e in events] == [
        "question_asked",
        "turn_read",
        "feature_routed",
        "tool_called",
        "answer_returned",
    ]
    assert events[0].detail["text"] == "KYC for ******3344?"  # masked in the log


async def test_playbook_run_survives_between_turns() -> None:
    await sync_to_async(playbook_services.upsert_playbook)(definition=BLOCKED_CARD)
    orchestrator = await make_orchestrator(FakeModel(), FakeToolClient())
    conversation_id = await start_conversation()

    first = await collect_events(
        orchestrator.ask(teller(), conversation_id, "card blocked", "troubleshooting")
    )
    second = await collect_events(
        orchestrator.ask(teller(), conversation_id, "done", reply_as="answer")
    )
    third = await collect_events(
        orchestrator.ask(teller(), conversation_id, "wrong pin", reply_as="answer")
    )

    def orders(events):
        return [e.step.order for e in events if isinstance(e, PlaybookStepShown)]

    assert (orders(first), orders(second), orders(third)) == ([1], [2], [3])
    run = await DjangoPlaybookStore().get_run(conversation_id)
    assert run.answers == {1: "confirm", 2: "wrong_pin"}
    assert run.feature_id == "troubleshooting"
