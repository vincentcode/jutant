"""Banking and HR in one deployment, end to end on their real servers (in-process, fake
systems): a person with a role in each uses both in one conversation, and each pack's server
sees them only as that pack's role."""

from datetime import date
from pathlib import Path

from core.actions.service import ActionService
from core.events import ActionProposed, FeatureSelected
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.orchestrator.orchestrator import Orchestrator
from core.packs import deployment
from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from core.types import Caller, PackRole, ToolCall
from packs.banking.mcp_servers import build_servers as banking_servers
from packs.hr.adapters.fake import DummyHr
from packs.hr.mcp_servers.hr.tools import create_server as hr_server
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
PACKS = Path(__file__).resolve().parents[2] / "packs"
AMA = Caller(
    "E1001",
    "teller",
    "staff",
    {"branch": "ACC-01"},
    packs={"banking": PackRole("teller", {"branch": "ACC-01"}), "hr": PackRole("employee")},
)
BANKER_ONLY = Caller(
    "S0002",
    "teller",
    "staff",
    {"branch": "ACC-01"},
    packs={"banking": PackRole("teller", {"branch": "ACC-01"})},
)


async def _setup():
    banking, hr = load_pack(PACKS / "banking"), load_pack(PACKS / "hr")
    joined = deployment.build([banking, hr], "Staff Assistant")
    dummy = DummyHr(today=date(2026, 10, 13))
    servers = {
        name: s.mcp
        for name, s in banking_servers(
            PolicyEngine(banking.rules, banking.field_rules), SECRET, "fake"
        ).items()
    }
    servers["hr"] = hr_server(
        dummy,
        dummy,
        dummy,
        PolicyEngine(hr.rules, hr.field_rules),
        SECRET,
        today=lambda: date(2026, 10, 13),
    ).mcp
    return joined, servers


async def test_each_packs_server_sees_the_role_there() -> None:
    joined, servers = await _setup()
    features = {f.id: f for f in joined.features}
    async with McpToolClient(servers, SECRET) as tools:
        audit = InMemoryAudit()
        gateway = ToolGateway(tools, ToolCatalog(tools), audit)
        await gateway.catalog.load()
        card = await gateway.execute(
            AMA,
            features["banking.card_lookup"],
            ToolCall("1", "cards.get_card", {"card_id": "CRD-3001"}),
        )
        leave = await gateway.execute(
            AMA, features["hr.my_leave"], ToolCall("2", "hr.leave_balance", {})
        )
        refused = await gateway.execute(
            BANKER_ONLY, features["hr.my_leave"], ToolCall("3", "hr.leave_balance", {})
        )
    assert card.ok  # the cards server saw a teller of ACC-01
    assert leave.ok and leave.data["Annual leave"].startswith("13 of 21")  # an employee, E1001
    assert refused.error == "denied"  # no role in HR: refused before reaching it
    assert ("tool_denied", "no_role_in_pack") in [
        (name, detail.get("error")) for _, name, detail in audit.events
    ]


async def test_one_conversation_routes_across_both_packs_without_choosing() -> None:
    joined, servers = await _setup()
    model = FakeModel(replies=[])  # routed by pattern, asked in code: no model call at all
    async with McpToolClient(servers, SECRET) as tools:
        conversations, audit = InMemoryConversationStore(), InMemoryAudit()
        registry = FeatureRegistry(joined.features)
        orchestrator = Orchestrator(
            model=model,
            tools=tools,
            conversations=conversations,
            playbooks=InMemoryPlaybookStore([]),
            audit=audit,
            registry=registry,
            router=FeatureRouter(model, registry, default=joined.default_feature),
            gateway=ToolGateway(tools, ToolCatalog(tools), audit),
            system_prompt=joined.system_prompt,
            system_prompts=joined.system_prompts,
            entity_types=joined.entity_types,
            actions=ActionService(
                joined.actions, InMemoryActionStore(), tools, conversations, audit
            ),
        )
        await orchestrator.load_tools()
        conversation = await conversations.create(AMA)
        events = await collect_events(
            orchestrator.ask(
                AMA, conversation, "Please book annual leave for me from 9 to 13 November 2026"
            )
        )
        assert (
            next(e for e in events if isinstance(e, FeatureSelected)).feature_id
            == "hr.leave_request"
        )
        card = next(e for e in events if isinstance(e, ActionProposed)).proposal
        assert card.draft.summary == "Annual leave, 9-13 Nov 2026"
        sent = await orchestrator.actions.confirm(AMA, card.id)
        assert (sent.status, sent.reference) == ("sent", "LV-2026-00290")
    assert model.calls == []
