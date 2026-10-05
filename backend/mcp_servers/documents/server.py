"""The documents MCP server process.

Run: python -m mcp_servers.documents.server

Searches the knowledge tables, embedding each query through the configured model provider.
Access rules and document labels come from the loaded pack.
"""

import config.bootstrap  # noqa: F401, I001  (sets up Django before any model is imported)

from django.conf import settings

from apps.knowledge.adapters import DjangoDocumentStore
from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from mcp_servers.common.guard import GuardedServer
from mcp_servers.common.server import serve
from mcp_servers.documents.tools import create_server
from providers.llm import factory as llm_factory


def build() -> GuardedServer:
    pack = load_pack(settings.JUTANT_PACK_PATH)
    return create_server(
        store=DjangoDocumentStore(
            llm_factory.build(settings), query_prefix=settings.JUTANT_EMBED_QUERY_PREFIX
        ),
        engine=PolicyEngine(pack.rules, pack.field_rules),
        secret=settings.JUTANT_CALLER_SECRET,
        readable=pack.readable_classifications,
    )


if __name__ == "__main__":
    serve(build(), settings.JUTANT_MCP_URLS["documents"])
