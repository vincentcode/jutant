"""The customer summary, assembled in code from the bank's systems.

Every figure is computed here, with decimal arithmetic, so the model only writes prose around
numbers it is given and never adds anything up itself.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from packs.banking.adapters.base import CoreBankingClient, ServiceCatalogClient

RECENT_TRANSACTIONS = 5


async def customer_summary(
    banking: CoreBankingClient, catalog: ServiceCatalogClient, customer_number: str
) -> dict[str, Any]:
    """Accounts and balances, the latest transactions across all accounts, open requests, flags."""
    customer = await banking.get_customer(customer_number)
    accounts = [await banking.get_account(number) for number in customer.get("accounts", [])]

    totals: dict[str, Decimal] = defaultdict(Decimal)
    for account in accounts:
        totals[account.get("currency", "")] += _amount(account.get("balance"))

    recent: list[dict[str, Any]] = []
    for account in accounts:
        rows = await banking.list_transactions(account["account_number"], limit=RECENT_TRANSACTIONS)
        recent.extend({**row, "account_number": account["account_number"]} for row in rows)
    recent.sort(key=lambda row: row.get("date", ""), reverse=True)

    requests = await catalog.open_requests(customer_number)
    return {
        "customer_number": customer_number,
        "name": customer.get("name"),
        "branch": customer.get("branch"),
        "flags": list(customer.get("flags", [])),
        "accounts": [
            {
                "account_number": a["account_number"],
                "type": a.get("type"),
                "status": a.get("status"),
                "currency": a.get("currency"),
                "balance": a.get("balance"),
            }
            for a in accounts
        ],
        "account_count": len(accounts),
        "dormant_accounts": [a["account_number"] for a in accounts if a.get("status") == "dormant"],
        "total_balance": {currency: f"{total:.2f}" for currency, total in sorted(totals.items())},
        "recent_transactions": [
            {
                k: row.get(k)
                for k in ("reference", "account_number", "date", "amount", "narration", "status")
            }
            for row in recent[:RECENT_TRANSACTIONS]
        ],
        "failed_transactions": [
            row["reference"] for row in recent if row.get("status") == "failed"
        ],
        "open_requests": requests,
    }


def _amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)
