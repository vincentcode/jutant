"""Every pack in `packs/` must load and pass the contract, against the tools its servers really
offer.

Each pack exposes its servers through `packs.<name>.mcp_servers.build_servers(engine, secret,
mode)`. The test starts those servers in-process on their fake adapters, together with the
platform's documents server, and checks the pack against the tool list they return: so a tool
added to a server without an access rule, or without the guard, fails the build.

`_template` is skipped: its policy path names the pack you create from it, not itself.
"""

import importlib
from pathlib import Path

import pytest

from core.packs.contract import check
from core.packs.loader import Pack, load_pack
from core.policy.engine import PolicyEngine
from core.types import ToolSpec
from mcp_servers.common.guard import GuardedServer
from mcp_servers.documents.tools import create_server as documents_server
from providers.mcp.client import McpToolClient

PACKS_DIR = Path(__file__).resolve().parents[2] / "packs"
PACKS = sorted(
    p for p in PACKS_DIR.iterdir() if (p / "pack.yaml").is_file() and not p.name.startswith("_")
)


def servers_for(pack: Pack) -> dict[str, GuardedServer]:
    engine = PolicyEngine(pack.rules, pack.field_rules)
    build_servers = importlib.import_module(f"packs.{pack.path.name}.mcp_servers").build_servers
    return {
        "documents": documents_server(None, engine, "", pack.readable_classifications),
        **build_servers(engine, "", "fake"),
    }


async def offered_tools(servers: dict[str, GuardedServer]) -> list[ToolSpec]:
    async with McpToolClient({name: s.mcp for name, s in servers.items()}, "") as client:
        return await client.list_tools()


@pytest.mark.parametrize("pack_dir", PACKS, ids=lambda p: p.name)
async def test_pack_passes_the_contract(pack_dir: Path) -> None:
    pack = load_pack(pack_dir)
    servers = servers_for(pack)
    for server in servers.values():
        assert await server.unguarded_tools() == [], server.name
    assert check(pack, await offered_tools(servers)) == []


def test_banking_pack_loads_its_content() -> None:
    pack = load_pack(PACKS_DIR / "banking")
    assert pack.manifest.name == "banking"
    assert len(pack.features) == 9  # eight kinds of help, and conversation
    assert {p.id for p in pack.playbooks} == {"blocked_card", "dormant_account", "failed_transfer"}
    assert pack.system_prompt.startswith("You are the Bank Staff Assistant.")
    assert all(f.prompt for f in pack.features)
    assert pack.readable_classifications("teller") == ["public", "internal"]
    assert pack.extraction_schemas["payslip"][0] == "employer"


def test_a_conversation_feature_takes_the_templates_own_examples() -> None:
    pack = load_pack(PACKS_DIR / "banking")
    [talk] = [f for f in pack.features if f.template == "conversation"]
    assert "What tools do you have?" in talk.route_examples  # the platform's
    assert "Hello, good morning" in talk.route_examples  # and the pack's
