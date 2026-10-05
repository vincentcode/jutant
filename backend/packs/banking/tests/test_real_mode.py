"""The pack's tools on the real HTTP clients: through the guard and the pack's rules, against
the mock bank, and with the bank down."""

from contextlib import asynccontextmanager

import httpx

from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from core.types import Caller, ToolCall
from packs.banking.adapters.core_banking import HttpCoreBankingClient
from packs.banking.adapters.http import BankHttp, Connection
from packs.banking.adapters.service_catalog import HttpServiceCatalogClient
from packs.banking.mcp_servers import PACK_DIR
from packs.banking.mcp_servers.services.tools import create_server as services_server
from packs.banking.mcp_servers.transactions.tools import create_server as transactions_server
from packs.banking.mock_bank import create_app
from providers.mcp.client import McpToolClient

SECRET = "s3cret"


def staff(role: str = "teller", branch: str = "ACC-01") -> Caller:
    return Caller("S1", role, "staff", {"branch": branch})


def bank_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused")


@asynccontextmanager
async def tools(transport: httpx.AsyncBaseTransport):
    pack = load_pack(PACK_DIR)
    engine = PolicyEngine(pack.rules, pack.field_rules)
    http = BankHttp(Connection("http://bank"), transport=transport)
    banking, catalog = HttpCoreBankingClient(http), HttpServiceCatalogClient(http)
    servers = {
        "transactions": transactions_server(banking, engine, SECRET),
        "services": services_server(banking, catalog, engine, SECRET),
    }
    try:
        async with McpToolClient({n: s.mcp for n, s in servers.items()}, SECRET) as client:
            yield client
    finally:
        await http.close()


async def call(transport, tool: str, caller: Caller | None = None, **arguments):
    async with tools(transport) as client:
        return await client.call(caller or staff(), ToolCall("1", tool, arguments))


MOCK_BANK = httpx.ASGITransport(app=create_app())


async def test_transactions_from_the_bank_over_http() -> None:
    result = await call(MOCK_BANK, "transactions.list", account_number="0011223344", limit=2)
    assert result.ok
    assert [t["reference"] for t in result.data["transactions"]] == ["TX-0003", "TX-0002"]


async def test_the_branch_rule_holds_on_bank_data() -> None:
    result = await call(
        MOCK_BANK, "transactions.list", staff(branch="KSI-02"), account_number="0011223344"
    )
    assert not result.ok and result.error == "denied"


async def test_the_customer_summary_is_assembled_from_the_bank() -> None:
    result = await call(
        MOCK_BANK, "services.customer_summary", staff("customer_service"), customer_number="C1001"
    )
    assert result.ok and result.data["total_balance"] == {"GHS": "6021.25"}


async def test_an_unknown_account_is_not_found() -> None:
    result = await call(MOCK_BANK, "transactions.list", account_number="0000000000")
    assert not result.ok and result.error == "not_found"


async def test_the_bank_being_down_is_an_upstream_error() -> None:
    result = await call(
        httpx.MockTransport(bank_down), "transactions.get_status", reference="TX-0002"
    )
    assert not result.ok and result.error == "upstream_error"
