"""Customer summary assembled in code from both adapters. All figures are computed here."""

from typing import Any

from packs.banking.adapters.base import CoreBankingClient, ServiceCatalogClient


async def customer_summary(
    banking: CoreBankingClient, catalog: ServiceCatalogClient, customer_number: str
) -> dict[str, Any]:
    """Accounts, balances, last 5 transactions, open requests and flags."""
    raise NotImplementedError
