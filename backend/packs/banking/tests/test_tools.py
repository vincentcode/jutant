"""The banking tools through the real guard and the pack's own rules, on the fake bank."""

from contextlib import asynccontextmanager

from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from core.types import Caller, Citation, ToolCall
from packs.banking.mcp_servers import PACK_DIR, build_servers
from providers.mcp.client import McpToolClient

SECRET = "s3cret"


def staff(role: str = "teller", branch: str = "ACC-01") -> Caller:
    return Caller("S1", role, "staff", {"branch": branch})


@asynccontextmanager
async def bank():
    pack = load_pack(PACK_DIR)
    servers = build_servers(PolicyEngine(pack.rules, pack.field_rules), SECRET, "fake")
    async with McpToolClient({n: s.mcp for n, s in servers.items()}, SECRET) as client:
        yield client


async def call(tool: str, caller: Caller | None = None, **arguments):
    async with bank() as client:
        return await client.call(caller or staff(), ToolCall("1", tool, arguments))


# --- transactions -------------------------------------------------------------


async def test_list_returns_newest_first_with_the_account_cited() -> None:
    result = await call("transactions.list", account_number="0011223344")
    assert result.ok
    refs = [t["reference"] for t in result.data["transactions"]]
    assert refs == ["TX-0003", "TX-0002", "TX-0001"]
    assert result.data["currency"] == "GHS"
    assert result.citations == (Citation("record", "Account", "0011223344"),)


async def test_list_filters() -> None:
    debits = await call("transactions.list", account_number="0011223344", direction="debit")
    assert [t["reference"] for t in debits.data["transactions"]] == ["TX-0002", "TX-0001"]
    since = await call("transactions.list", account_number="0011223344", from_date="2026-09-30")
    assert [t["reference"] for t in since.data["transactions"]] == ["TX-0003", "TX-0002"]
    one = await call("transactions.list", account_number="0011223344", limit=1)
    assert len(one.data["transactions"]) == 1


async def test_bad_date_and_bad_direction_are_invalid_arguments() -> None:
    bad_date = await call("transactions.list", account_number="0011223344", from_date="30/09/2026")
    assert bad_date.error == "invalid_arguments"
    assert "YYYY-MM-DD" in bad_date.data[0]
    bad_direction = await call("transactions.list", account_number="0011223344", direction="up")
    assert bad_direction.error == "invalid_arguments"


async def test_failed_transfer_status_and_reason() -> None:
    result = await call("transactions.get_status", reference="tx-0002")
    assert result.ok
    assert (result.data["status"], result.data["failure_code"]) == ("failed", "E51")
    assert result.data["failure_reason"] == "Beneficiary account closed"
    assert result.citations == (Citation("record", "Transaction", "TX-0002"),)


async def test_teller_cannot_see_another_branchs_account() -> None:
    other = await call("transactions.list", staff(branch="KSI-02"), account_number="0011223344")
    assert (other.ok, other.error, other.data) == (False, "denied", None)
    status = await call("transactions.get_status", staff(branch="KSI-02"), reference="TX-0002")
    assert status.error == "denied"


async def test_branch_manager_sees_any_branch() -> None:
    result = await call(
        "transactions.list", staff("branch_manager", "KSI-02"), account_number="0011223344"
    )
    assert result.ok


async def test_unknown_account_or_reference_is_not_found() -> None:
    assert (await call("transactions.list", account_number="000")).error == "not_found"
    assert (await call("transactions.get_status", reference="TX-9999")).error == "not_found"


# --- services -----------------------------------------------------------------


async def test_product_search_and_details() -> None:
    found = await call("services.search_products", query="savings")
    assert found.data == [{"code": "SAV-STD", "name": "Standard Savings"}]
    product = await call("services.get_product", product_code="sav-std")
    assert product.data["rate"] == "8.5%"
    assert product.citations == (Citation("record", "Product", "SAV-STD"),)


async def test_requirements_accept_plain_words() -> None:
    result = await call("services.get_requirements", request_type="Joint account opening")
    assert result.data["forms"] == ["Account opening form", "Joint mandate form"]
    assert result.citations == (Citation("record", "Requirements", "joint_account_opening"),)


async def test_customer_summary_roles_and_branch() -> None:
    teller = await call("services.customer_summary", staff("teller"), customer_number="C1001")
    assert teller.error == "denied"
    own = await call(
        "services.customer_summary", staff("customer_service"), customer_number="c1001"
    )
    assert own.ok
    assert own.citations == (Citation("record", "Customer", "C1001"),)
    other = await call(
        "services.customer_summary", staff("customer_service", "KSI-02"), customer_number="C1001"
    )
    assert other.error == "denied"


async def test_every_tool_is_guarded_and_has_a_rule() -> None:
    pack = load_pack(PACK_DIR)
    servers = build_servers(PolicyEngine(pack.rules), SECRET, "fake")
    names = []
    for server in servers.values():
        assert await server.unguarded_tools() == []
        names += await server.tool_names()
    assert set(names) <= {rule.tool for rule in pack.rules}
