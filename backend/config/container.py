"""Builds the orchestrator with its real dependencies.

This is the only place that decides which implementation (Django store, Ollama, MCP client)
stands behind each interface the core depends on. Tests build the orchestrator with fakes.
"""

from dataclasses import dataclass

from django.conf import settings

from apps.audit.adapters import DjangoAuditSink
from apps.conversation.adapters import DjangoConversationStore
from apps.playbooks.adapters import DjangoPlaybookStore
from core.errors import PackContractError
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.orchestrator.orchestrator import Orchestrator
from core.packs.contract import check
from core.packs.loader import Pack, load_pack
from core.tools.catalog import ToolCatalog
from core.tools.gateway import ToolGateway
from providers.llm import factory as llm_factory
from providers.mcp.client import McpToolClient


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
    """The loaded pack, the orchestrator and the MCP connections behind it."""

    pack: Pack
    orchestrator: Orchestrator
    tool_client: McpToolClient

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


def build_runtime() -> Runtime:
    pack = load_pack(settings.JUTANT_PACK_PATH)
    model = llm_factory.build(settings)
    tool_client = McpToolClient(servers=resolve_servers(pack), secret=settings.JUTANT_CALLER_SECRET)
    registry = FeatureRegistry(pack.features)
    audit = DjangoAuditSink()
    gateway = ToolGateway(tool_client, ToolCatalog(tool_client), audit)
    orchestrator = Orchestrator(
        model=model,
        tools=tool_client,
        conversations=DjangoConversationStore(),
        playbooks=DjangoPlaybookStore(),
        audit=audit,
        registry=registry,
        router=FeatureRouter(model, registry, default=pack.manifest.default_feature),
        gateway=gateway,
        max_steps=settings.JUTANT_MAX_STEPS,
        history_limit=settings.JUTANT_HISTORY_LIMIT,
        system_prompt=pack.system_prompt,
        extraction_schemas=pack.extraction_schemas,
    )
    return Runtime(pack, orchestrator, tool_client)
