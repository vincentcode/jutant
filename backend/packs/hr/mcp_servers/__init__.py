"""The HR pack's MCP server.

`build_servers` is the pack's entry point for its servers: the platform's contract check uses
it to read every tool the pack offers, and the server process uses it to build its server. One
server, `hr`, holds the three systems' tools, so a request filed is at once in the employee's
requests and balance.
"""

import os
from pathlib import Path

from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from mcp_servers.common.guard import GuardedServer
from packs.hr import adapters

PACK_DIR = Path(__file__).resolve().parents[1]


def build_servers(
    engine: PolicyEngine, secret: str, mode: str | None = None
) -> dict[str, GuardedServer]:
    """Every server of the pack, by name, on the dummy or real HR systems."""
    from packs.hr.mcp_servers.hr.tools import create_server

    systems = adapters.build(mode)
    return {"hr": create_server(systems.records, systems.leave, systems.helpdesk, engine, secret)}


def build_from_environment(name: str) -> GuardedServer:
    """The named server, configured as a deployed process: rules from the pack, the shared
    caller secret and the adapter mode from the environment."""
    pack = load_pack(PACK_DIR)
    engine = PolicyEngine(pack.rules, pack.field_rules)
    return build_servers(engine, os.environ["JUTANT_CALLER_SECRET"])[name]
