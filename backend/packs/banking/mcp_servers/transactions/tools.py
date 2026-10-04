"""Tools over the core banking system: recent transactions and transfer status.

Every tool is wrapped in @guarded_tool, which checks access and hides fields before data
leaves the server.
"""

from typing import Any

from packs.banking.adapters.base import CoreBankingClient


async def list_transactions(
    client: CoreBankingClient,
    account_number: str,
    from_date: str | None = None,
    to_date: str | None = None,
    direction: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    raise NotImplementedError


async def get_status(client: CoreBankingClient, reference: str) -> dict[str, Any]:
    raise NotImplementedError
