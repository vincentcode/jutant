"""Builders for core tests: a fully wired orchestrator on fakes, and small value helpers."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from core.events import Completed, Event, Failed
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.orchestrator.orchestrator import Orchestrator
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from core.types import (
    Answer,
    Caller,
    Citation,
    Feature,
    Playbook,
    PlaybookStep,
    ToolResult,
    ToolSpec,
)
from providers.llm.fake import FakeModel
from providers.mcp.fake import FakeToolClient
from tests.fakes import InMemoryAudit, InMemoryConversationStore, InMemoryPlaybookStore

QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}

FEATURES = (
    Feature(
        "policy_qa",
        "document_qa",
        "Policy Q&A",
        "Questions about policy and procedures.",
        "Search documents first.",
        ("documents.search",),
        (),
    ),
    Feature(
        "transaction_lookup",
        "record_lookup",
        "Transaction lookup",
        "Account activity and why a transfer failed.",
        "Look up transactions.",
        ("transactions.get_status",),
        (),
    ),
    Feature(
        "customer_360",
        "record_summary",
        "Customer 360",
        "Summary of a customer.",
        "Summarise the customer.",
        ("services.customer_summary",),
        ("branch_manager",),
    ),
    Feature(
        "troubleshooting",
        "guided_playbook",
        "Troubleshooting",
        "Step-by-step help for a blocked card.",
        "",
        (),
        (),
    ),
    Feature(
        "extraction",
        "document_extraction",
        "Extraction",
        "Pull fields from a document.",
        "",
        ("documents.get",),
        (),
    ),
)

BLOCKED_CARD = Playbook(
    "blocked_card",
    "Blocked card",
    "Card is blocked or declined.",
    (
        PlaybookStep(1, "Verify", "Verify the customer.", ("staff",)),
        PlaybookStep(
            2,
            "Reason",
            "Which reason is shown?",
            ("staff",),
            "choice",
            ("wrong_pin", "fraud_hold"),
            {"wrong_pin": 3, "fraud_hold": 4},
        ),
        PlaybookStep(
            3, "Reset PIN", "Reset the PIN counter.", ("staff", "customer"), next_on={"confirm": 5}
        ),
        PlaybookStep(4, "Refer", "Refer to fraud.", ("staff",)),
        PlaybookStep(5, "Close", "Confirm the outcome.", ("staff", "customer"), "none"),
    ),
)


def teller(**attributes: Any) -> Caller:
    return Caller("S001", "teller", "staff", attributes or {"branch": "ACC-01"})


def spec(name: str, schema: dict[str, Any] | None = None) -> ToolSpec:
    return ToolSpec(name, name, schema or QUERY_SCHEMA)


def doc_result(title: str, section: str, text: str = "Policy text.") -> ToolResult:
    return ToolResult(
        "",
        ok=True,
        data=[{"title": title, "section": section, "text": text}],
        citations=(Citation("document", title, section),),
    )


def record_result(kind: str, reference: str, data: dict[str, Any]) -> ToolResult:
    return ToolResult("", ok=True, data=data, citations=(Citation("record", kind, reference),))


@dataclass
class Rig:
    orchestrator: Orchestrator
    model: FakeModel
    tools: FakeToolClient
    conversations: InMemoryConversationStore
    playbooks: InMemoryPlaybookStore
    audit: InMemoryAudit
    specs: list[ToolSpec] = field(default_factory=list)


async def make_rig(
    model: FakeModel | None = None,
    results: dict[str, Any] | None = None,
    specs: list[ToolSpec] | None = None,
    features: tuple[Feature, ...] = FEATURES,
    playbooks: list[Playbook] | None = None,
    max_steps: int = 4,
    extraction_schemas: dict[str, list[str]] | None = None,
) -> Rig:
    model = model or FakeModel()
    tools = FakeToolClient(
        results=results or {},
        specs=specs if specs is not None else [spec(t) for f in features for t in f.tools],
    )
    conversations = InMemoryConversationStore()
    store = InMemoryPlaybookStore(playbooks if playbooks is not None else [BLOCKED_CARD])
    audit = InMemoryAudit()
    registry = FeatureRegistry(features)
    gateway = ToolGateway(tools, ToolCatalog(tools), audit)
    orchestrator = Orchestrator(
        model=model,
        tools=tools,
        conversations=conversations,
        playbooks=store,
        audit=audit,
        registry=registry,
        router=FeatureRouter(model, registry, default="policy_qa"),
        gateway=gateway,
        max_steps=max_steps,
        system_prompt="You help bank staff.",
        extraction_schemas=extraction_schemas,
    )
    await orchestrator.load_tools()
    return Rig(orchestrator, model, tools, conversations, store, audit)


async def collect_events(events: AsyncIterator[Event]) -> list[Event]:
    return [event async for event in events]


async def final_answer(events: AsyncIterator[Event]) -> Answer:
    collected = await collect_events(events)
    last = collected[-1]
    if isinstance(last, Failed):
        raise AssertionError(f"turn failed: {last.reason}")
    assert isinstance(last, Completed), last
    return last.answer
