"""This pack's MCP servers.

`build_servers` is the pack's entry point for its servers. The platform's contract check calls
it to read every tool the pack offers, and each server process calls it to build its server. See
`packs/banking/mcp_servers` for a worked example:

    def build_servers(engine, secret, mode=None):
        systems = adapters.build(mode)                 # fake or real clients for your systems
        return {"orders": orders_server(systems.orders, engine, secret)}

Each server is a `mcp_servers.common.guard.GuardedServer`, and every tool is registered with
`server.tool(...)`, so it runs behind the access rules.
"""

from core.policy.engine import PolicyEngine
from mcp_servers.common.guard import GuardedServer


def build_servers(
    engine: PolicyEngine, secret: str, mode: str | None = None
) -> dict[str, GuardedServer]:
    return {}
