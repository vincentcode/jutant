"""The documents MCP server process.

Run: python -m mcp_servers.documents.server

Searches the knowledge tables, embedding each query through the configured model provider.
Shared by every loaded pack: each call is checked against the rules and labels of the pack the
caller acts in, and finds that pack's documents and the shared ones.
"""

import config.bootstrap  # noqa: F401, I001  (sets up Django before any model is imported)

from django.conf import settings

from apps.knowledge.adapters import DjangoDocumentStore
from config.container import load_deployment
from core.policy.engine import PackPolicies, PolicyEngine
from mcp_servers.common.guard import GuardedServer
from mcp_servers.common.server import serve
from mcp_servers.documents.tools import create_server
from providers.llm import factory as llm_factory


def build() -> GuardedServer:
    deployment = load_deployment()
    return create_server(
        store=DjangoDocumentStore(
            llm_factory.build(settings), query_prefix=settings.JUTANT_EMBED_QUERY_PREFIX
        ),
        engine=PackPolicies(
            {p.manifest.name: PolicyEngine(p.rules, p.field_rules) for p in deployment.packs}
        ),
        secret=settings.JUTANT_CALLER_SECRET,
        readable=deployment.readable_classifications,
    )


if __name__ == "__main__":
    serve(build(), settings.JUTANT_MCP_URLS["documents"])
