"""Every pack in `packs/` must load and pass the contract.

`_template` is skipped: its policy path names the pack you create from it, not itself.
"""

from pathlib import Path

import pytest

from core.packs.contract import check
from core.packs.loader import load_pack
from core.types import ToolSpec

PACKS_DIR = Path(__file__).resolve().parents[2] / "packs"
PACKS = sorted(
    p for p in PACKS_DIR.iterdir() if (p / "pack.yaml").is_file() and not p.name.startswith("_")
)

# The tools each pack's servers will expose. TODO: read these from the MCP servers in-process
# once they are written, so a tool added to a server without a rule fails this test.
SERVER_TOOLS = {
    "banking": [
        "documents.search",
        "documents.get",
        "transactions.list",
        "transactions.get_status",
        "services.search_products",
        "services.get_product",
        "services.get_requirements",
        "services.customer_summary",
    ],
}


@pytest.mark.parametrize("pack_dir", PACKS, ids=lambda p: p.name)
def test_pack_passes_the_contract(pack_dir: Path) -> None:
    pack = load_pack(pack_dir)
    specs = [ToolSpec(name, name, {"type": "object"}) for name in SERVER_TOOLS[pack_dir.name]]
    assert check(pack, specs) == []


def test_banking_pack_loads_its_content() -> None:
    pack = load_pack(PACKS_DIR / "banking")
    assert pack.manifest.name == "banking"
    assert len(pack.features) == 8
    assert {p.id for p in pack.playbooks} == {"blocked_card", "dormant_account", "failed_transfer"}
    assert pack.system_prompt.startswith("You are the Bank Staff Assistant.")
    assert all(f.prompt for f in pack.features)
    assert pack.readable_classifications("teller") == ["public", "internal"]
    assert pack.extraction_schemas["payslip"][0] == "employer"
