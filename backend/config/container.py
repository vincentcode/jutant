"""Builds the orchestrator with its real dependencies.

This is the only place that decides which implementation (Django store, Ollama, MCP client)
stands behind each interface the core depends on. Tests build the orchestrator with fakes.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.conf import settings

from apps.audit.adapters import DjangoAuditSink
from apps.conversation.adapters import DjangoConversationStore
from apps.identity.adapters import DjangoIdentityProvider, LoginLimits
from apps.knowledge.adapters import DocumentLibrary
from apps.playbooks.adapters import DjangoPlaybookStore
from core.errors import PackContractError
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.observability import TraceContent
from core.orchestrator.orchestrator import Orchestrator, TurnMode
from core.packs.contract import check
from core.packs.loader import Pack, load_pack
from core.ports import ModelProvider
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from providers import tracing
from providers.llm import factory as llm_factory
from providers.mcp.client import McpToolClient
from providers.ocr.base import OcrEngine
from providers.ocr.tesseract import TesseractOcr
from providers.tracing.feedback import FeedbackSink, NoFeedbackSink


def resolve_servers(pack: Pack) -> dict[str, str]:
    """Map each MCP server named in the manifest to its URL."""
    servers: dict[str, str] = {}
    for ref in pack.manifest.mcp_servers:
        name = ref.platform or ref.pack
        if name is None:
            raise ValueError("MCP server reference needs 'platform' or 'pack'")
        servers[name] = ref.url or settings.JUTANT_MCP_URLS[name]
    return servers


@dataclass
class Runtime:
    """Everything the API serves with: the loaded pack, the orchestrator and the MCP
    connections behind it, and the stores the API reads directly."""

    pack: Pack
    orchestrator: Orchestrator
    tool_client: McpToolClient
    identity: DjangoIdentityProvider
    conversations: DjangoConversationStore
    ocr: OcrEngine | None
    feedback: FeedbackSink = field(default_factory=NoFeedbackSink)  # ratings, to traces too
    library: DocumentLibrary = field(default_factory=DocumentLibrary)  # the Knowledge panel

    async def start(self) -> None:
        """Connect to the MCP servers, read their tools and check the pack contract.

        The process refuses to start if the pack fails, so a broken pack never serves staff.
        """
        await self.tool_client.connect()
        await self.orchestrator.load_tools()
        problems = check(self.pack, self.orchestrator.gateway.catalog.specs)
        if problems:
            await self.tool_client.close()
            raise PackContractError(problems)

    async def stop(self) -> None:
        await self.tool_client.close()
        shutdown_tracing = getattr(self.orchestrator.tracer, "shutdown", None)
        if shutdown_tracing is not None:
            shutdown_tracing()  # sends the spans still waiting
        close_model = getattr(self.orchestrator.model, "close", None)
        if close_model is not None:
            await close_model()
        close_feedback = getattr(self.feedback, "close", None)
        if close_feedback is not None:
            await close_feedback()


def build_runtime(
    model: ModelProvider | None = None,
    servers: dict[str, Any] | None = None,
    ocr: OcrEngine | None = None,
) -> Runtime:
    """The deployment's runtime. Tests pass a fake model and in-process MCP servers instead of
    the configured ones; everything else is wired exactly as deployed."""
    pack = load_pack(settings.JUTANT_PACK_PATH)
    model = model or llm_factory.build(settings)
    tool_client = McpToolClient(
        servers=servers or resolve_servers(pack), secret=settings.JUTANT_CALLER_SECRET
    )
    conversations = DjangoConversationStore()
    registry = FeatureRegistry(pack.features)
    audit = DjangoAuditSink()
    gateway = ToolGateway(tool_client, ToolCatalog(tool_client), audit)
    orchestrator = Orchestrator(
        model=model,
        tools=tool_client,
        conversations=conversations,
        playbooks=DjangoPlaybookStore(),
        audit=audit,
        registry=registry,
        router=FeatureRouter(
            model,
            registry,
            default=pack.manifest.default_feature,
            embed_prefix=settings.JUTANT_EMBED_ROUTE_PREFIX,
            min_similarity=settings.JUTANT_ROUTE_MIN_SIMILARITY,
            min_margin=settings.JUTANT_ROUTE_MIN_MARGIN,
        ),
        gateway=gateway,
        max_steps=settings.JUTANT_MAX_STEPS,
        history_limit=settings.JUTANT_HISTORY_LIMIT,
        system_prompt=pack.system_prompt,
        extraction_schemas=pack.extraction_schemas,
        tracer=tracing.build(settings),
        trace_content=TraceContent(include=settings.JUTANT_TRACE_CONTENT),
        entity_types=pack.entity_types,
        turn_mode=_turn_mode(settings.JUTANT_TURN_MODE),
        tool_labels=pack.manifest.tool_labels,
    )
    return Runtime(
        feedback=tracing.feedback_sink(settings),
        pack=pack,
        orchestrator=orchestrator,
        tool_client=tool_client,
        identity=DjangoIdentityProvider(
            pack.manifest.roles,
            LoginLimits(
                per_user=settings.JUTANT_LOGIN_MAX_FAILURES,
                per_ip=settings.JUTANT_LOGIN_MAX_FAILURES_PER_IP,
                window=timedelta(minutes=settings.JUTANT_LOGIN_WINDOW_MIN),
            ),
        ),
        conversations=conversations,
        ocr=ocr or TesseractOcr(),
    )


def _turn_mode(name: str) -> TurnMode:
    return name if name in ("route", "hybrid", "agent") else "hybrid"  # type: ignore[return-value]
