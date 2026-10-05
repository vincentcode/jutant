"""Tools over the service catalogue: products, request requirements, customer summary.

Every tool is registered on a GuardedServer, which checks access and hides fields before data
leaves the server. The customer summary returns the customer as its record, so the branch rule
can check the caller's branch against the customer's.
"""

import re

from core.policy.engine import PolicyEngine
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolOutput
from packs.banking.adapters.base import CoreBankingClient, ServiceCatalogClient
from packs.banking.mcp_servers.services.aggregators import customer_summary


def create_server(
    banking: CoreBankingClient,
    catalog: ServiceCatalogClient,
    engine: PolicyEngine,
    secret: str,
) -> GuardedServer:
    server = GuardedServer("services", engine, secret)

    @server.tool("search_products", "Find bank products by name or code. Returns codes and names.")
    async def search_products(caller: Caller, query: str) -> ToolOutput:
        products = await catalog.search_products(query.strip())
        return ToolOutput(
            data=products,
            citations=tuple(Citation("record", "Product", p["code"]) for p in products),
        )

    @server.tool(
        "get_product",
        "Rates, fees, eligibility and required documents for one product, by its code.",
    )
    async def get_product(caller: Caller, product_code: str) -> ToolOutput:
        code = product_code.strip().upper()
        return ToolOutput(
            data=await catalog.get_product(code),
            citations=(Citation("record", "Product", code),),
        )

    @server.tool(
        "get_requirements",
        "Forms, signatures and approvals a request needs, e.g. joint_account_opening.",
    )
    async def get_requirements(caller: Caller, request_type: str) -> ToolOutput:
        key = _request_key(request_type)
        return ToolOutput(
            data=await catalog.get_requirements(key),
            citations=(Citation("record", "Requirements", key),),
        )

    @server.tool(
        "customer_summary",
        "One-screen summary of a customer: accounts, balances, recent activity, open requests.",
    )
    async def summary(caller: Caller, customer_number: str) -> ToolOutput:
        number = customer_number.strip().upper()
        data = await customer_summary(banking, catalog, number)
        return ToolOutput(
            data=data,
            citations=(Citation("record", "Customer", number),),
            record={"branch": data["branch"]},
        )

    return server


def _request_key(request_type: str) -> str:
    """'Joint account opening' and 'joint-account-opening' both mean joint_account_opening."""
    return re.sub(r"[\s-]+", "_", request_type.strip().lower())
