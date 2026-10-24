"""A leave request end to end: the real orchestrator and the HR pack's server, a scripted
model. The employee is asked, in code, for what is missing; the request is checked and shown as
a card in code; it is sent only when confirmed. The model is never asked anything."""

from datetime import date

from core.actions.service import ActionService
from core.events import ActionProposed, Clarify, Completed, TextDelta
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.orchestrator.orchestrator import CHECK_THE_REQUEST, Orchestrator
from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from core.types import Caller
from packs.hr.adapters.fake import DummyHr
from packs.hr.mcp_servers import PACK_DIR
from packs.hr.mcp_servers.hr.tools import create_server
from providers.llm.fake import FakeModel
from providers.mcp.client import McpToolClient
from tests.builders import collect_events
from tests.fakes import (
    InMemoryActionStore,
    InMemoryAudit,
    InMemoryConversationStore,
    InMemoryPlaybookStore,
)

SECRET = "s3cret"
TODAY = date(2026, 10, 13)
ABENA = Caller("E1001", "employee", "staff")


async def test_asked_in_code_proposed_in_code_sent_once_confirmed() -> None:
    pack = load_pack(PACK_DIR)
    hr = DummyHr(today=TODAY)
    server = create_server(
        hr, hr, hr, PolicyEngine(pack.rules, pack.field_rules), SECRET, today=lambda: TODAY
    )
    model = FakeModel(replies=[])  # any call to the model would fail the test
    async with McpToolClient({"hr": server.mcp}, SECRET) as tools:
        orchestrator, actions, conversations = await _wired(pack, model, tools)
        conversation = await conversations.create(ABENA)

        asked = await collect_events(
            orchestrator.ask(ABENA, conversation, "I need some leave", "leave_request")
        )
        which = next(e for e in asked if isinstance(e, Clarify))
        assert which.question == "Which kind of leave?"
        assert ("Annual leave") in [c.title for c in which.choices]

        dates = await collect_events(orchestrator.ask(ABENA, conversation, "Annual leave"))
        assert any("Which days?" in e.text for e in dates if isinstance(e, TextDelta))

        proposed = await collect_events(
            orchestrator.ask(ABENA, conversation, "9 to 13 November 2026")
        )
        card = next(e for e in proposed if isinstance(e, ActionProposed)).proposal
        assert card.draft.summary == "Annual leave, 9-13 Nov 2026"
        assert isinstance(proposed[-1], Completed)
        assert proposed[-1].answer.text == CHECK_THE_REQUEST
        assert await hr.leave_requests("E1001") == (
            await DummyHr(today=TODAY).leave_requests("E1001")
        )

        sent = await actions.confirm(ABENA, card.id)
        assert (sent.status, sent.reference) == ("sent", "LV-2026-00290")
        assert sent.outcome == "Waiting for Kofi Mensah"
        assert model.calls == []


async def test_a_request_the_rules_refuse_says_why_in_code() -> None:
    """Made in code from what staff gave, a refused request is answered with the refusal. It is
    not a record to pick a field from: that answered "the record does not show that"."""
    pack = load_pack(PACK_DIR)
    hr = DummyHr(today=TODAY)
    server = create_server(
        hr, hr, hr, PolicyEngine(pack.rules, pack.field_rules), SECRET, today=lambda: TODAY
    )
    model = FakeModel(replies=[])
    async with McpToolClient({"hr": server.mcp}, SECRET) as tools:
        orchestrator, actions, conversations = await _wired(pack, model, tools)
        asked = "Book annual leave from 9 to 13 November 2026"
        first = await collect_events(
            orchestrator.ask(ABENA, await conversations.create(ABENA), asked, "leave_request")
        )
        card = next(e for e in first if isinstance(e, ActionProposed)).proposal
        await actions.confirm(ABENA, card.id)

        again = await collect_events(
            orchestrator.ask(ABENA, await conversations.create(ABENA), asked, "leave_request")
        )
        assert not any(isinstance(e, ActionProposed) for e in again)
        assert isinstance(again[-1], Completed)
        assert again[-1].answer.text.startswith("You already have leave for 9")
        assert model.calls == []


async def _wired(pack, model: FakeModel, tools: McpToolClient):
    conversations, audit = InMemoryConversationStore(), InMemoryAudit()
    registry = FeatureRegistry(pack.features)
    actions = ActionService(pack.actions, InMemoryActionStore(), tools, conversations, audit)
    orchestrator = Orchestrator(
        model=model,
        tools=tools,
        conversations=conversations,
        playbooks=InMemoryPlaybookStore([]),
        audit=audit,
        registry=registry,
        router=FeatureRouter(model, registry, default="conversation"),
        gateway=ToolGateway(tools, ToolCatalog(tools), audit),
        system_prompt=pack.system_prompt,
        entity_types=pack.entity_types,
        actions=actions,
    )
    await orchestrator.load_tools()
    return orchestrator, actions, conversations
