"""The banking pack end to end: its manifest, prompts, playbooks and rules, its real MCP servers
in-process on the fake bank, and the orchestrator, with a scripted model."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from core.errors import PolicyDenied
from core.events import Failed, PlaybookStepShown, TextDelta, ToolFinished
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.orchestrator.orchestrator import Orchestrator
from core.packs.loader import load_pack
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from core.types import Caller, Citation, ModelReply, ToolCall
from providers.llm.fake import FakeModel
from providers.mcp.client import McpToolClient
from tests.builders import collect_events
from tests.fakes import InMemoryAudit, InMemoryConversationStore, InMemoryPlaybookStore
from tests.packs.test_contract import PACKS_DIR, servers_for

SECRET = ""  # servers_for builds the servers with an empty secret


def staff(role: str = "teller", branch: str = "ACC-01") -> Caller:
    return Caller("S1", role, "staff", {"branch": branch})


@asynccontextmanager
async def banking_assistant(model: FakeModel):
    pack = load_pack(PACKS_DIR / "banking")
    servers = servers_for(pack)
    async with McpToolClient({n: s.mcp for n, s in servers.items()}, SECRET) as tools:
        audit = InMemoryAudit()
        registry = FeatureRegistry(pack.features)
        orchestrator = Orchestrator(
            model=model,
            tools=tools,
            conversations=InMemoryConversationStore(),
            playbooks=InMemoryPlaybookStore(list(pack.playbooks)),
            audit=audit,
            registry=registry,
            router=FeatureRouter(model, registry, default=pack.manifest.default_feature),
            gateway=ToolGateway(tools, ToolCatalog(tools), audit),
            system_prompt=pack.system_prompt,
            extraction_schemas=pack.extraction_schemas,
        )
        await orchestrator.load_tools()
        yield orchestrator


def calls(name: str, **arguments) -> ModelReply:
    return ModelReply(None, (ToolCall("1", name, arguments),))


async def test_teller_asks_why_a_transfer_failed() -> None:
    model = FakeModel(
        replies=[
            calls("transactions.get_status", reference="TX-0002"),
            ModelReply("TX-0002 failed (E51): the beneficiary account is closed."),
        ]
    )
    async with banking_assistant(model) as assistant:
        events = await collect_events(
            assistant.ask(staff(), uuid4(), "Why did TX-0002 fail?", "transaction_lookup")
        )

    answer = events[-1].answer
    assert answer.citations == (Citation("record", "Transaction", "TX-0002"),)
    system_prompt = model.calls[0].messages[0].content
    assert system_prompt.startswith("You are the Bank Staff Assistant.")
    assert "transactions.get_status" in system_prompt  # the feature's own prompt
    assert [s.name for s in model.calls[0].tools] == [
        "transactions.list",
        "transactions.get_status",
    ]


async def test_another_branchs_customer_is_refused_at_once() -> None:
    model = FakeModel()  # the customer number is looked up in code; the model is never asked
    async with banking_assistant(model) as assistant:
        events = await collect_events(
            assistant.ask(
                staff("customer_service", "KSI-02"), uuid4(), "Summary of C1001", "customer_360"
            )
        )

    result = next(e.result for e in events if isinstance(e, ToolFinished))
    assert result.error == "denied"
    assert events[-1] == Failed("denied")
    assert not any(isinstance(e, TextDelta) for e in events)  # nothing is said about C1001
    assert model.calls == []


async def test_teller_cannot_open_the_customer_summary_feature() -> None:
    async with banking_assistant(FakeModel()) as assistant:
        with pytest.raises(PolicyDenied):
            await collect_events(
                assistant.ask(staff(), uuid4(), "Summary of C1001", "customer_360")
            )


async def test_customer_summary_for_own_branch() -> None:
    model = FakeModel(
        replies=[
            calls("services.customer_summary", customer_number="C1001"),
            ModelReply("Ama Mensah holds two accounts totalling GHS 6,021.25."),
        ]
    )
    async with banking_assistant(model) as assistant:
        answer = (
            await collect_events(
                assistant.ask(
                    staff("customer_service"), uuid4(), "Summary of C1001", "customer_360"
                )
            )
        )[-1].answer
    assert answer.citations == (Citation("record", "Customer", "C1001"),)
    tool_message = model.calls[1].messages[-1].content
    assert '"total_balance":{"GHS":"6021.25"}' in tool_message  # the figure came from code


async def test_router_and_playbook_from_the_pack() -> None:
    model = FakeModel(replies=[ModelReply("troubleshooting"), ModelReply("blocked_card")])
    async with banking_assistant(model) as assistant:
        events = await collect_events(
            assistant.ask(staff(), uuid4(), "The customer's card is blocked")
        )
    step = next(e for e in events if isinstance(e, PlaybookStepShown))
    assert (step.playbook_id, step.step.order) == ("blocked_card", 1)
