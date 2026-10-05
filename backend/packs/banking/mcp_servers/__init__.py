"""The banking pack's MCP servers.

`build_servers` is the pack's entry point for its servers: the platform's contract check uses
it to read every tool the pack offers, and each server process uses it to build its own server.
"""

import os
from pathlib import Path

from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from mcp_servers.common.guard import GuardedServer
from packs.banking import adapters

PACK_DIR = Path(__file__).resolve().parents[1]


def build_servers(
    engine: PolicyEngine, secret: str, mode: str | None = None
) -> dict[str, GuardedServer]:
    """Every server of the pack, by name, on the fake or real bank systems."""
    from packs.banking.mcp_servers.services.tools import create_server as services_server
    from packs.banking.mcp_servers.transactions.tools import create_server as transactions_server

    systems = adapters.build(mode)
    return {
        "transactions": transactions_server(systems.banking, engine, secret),
        "services": services_server(systems.banking, systems.catalog, engine, secret),
    }


def build_from_environment(name: str) -> GuardedServer:
    """The named server, configured as a deployed process: rules from the pack, the shared
    caller secret and the adapter mode from the environment."""
    pack = load_pack(PACK_DIR)
    engine = PolicyEngine(pack.rules, pack.field_rules)
    return build_servers(engine, os.environ["JUTANT_CALLER_SECRET"])[name]
