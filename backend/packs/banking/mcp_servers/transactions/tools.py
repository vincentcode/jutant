"""Tools over the core banking system: recent transactions and transfer status.

Every tool is registered on a GuardedServer, which checks access and hides fields before data
leaves the server. Each tool returns the account it read as the record, so the branch rule can
check the caller's branch against the account's.
"""

from datetime import date
from typing import Any, Literal

from core.policy.engine import PolicyEngine
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolInputError, ToolOutput
from packs.banking.adapters.base import CoreBankingClient

MAX_TRANSACTIONS = 20
TRANSACTION_FIELDS = ("reference", "date", "amount", "direction", "narration", "status")


def create_server(banking: CoreBankingClient, engine: PolicyEngine, secret: str) -> GuardedServer:
    server = GuardedServer("transactions", engine, secret)

    @server.tool(
        "list",
        "Recent transactions on one account, newest first. Dates are YYYY-MM-DD.",
    )
    async def list_transactions(
        caller: Caller,
        account_number: str,
        from_date: str | None = None,
        to_date: str | None = None,
        direction: Literal["debit", "credit"] | None = None,
        limit: int = 5,
    ) -> ToolOutput:
        filters: dict[str, Any] = {"limit": max(1, min(limit, MAX_TRANSACTIONS))}
        if from_date:
            filters["from_date"] = _iso_date(from_date)
        if to_date:
            filters["to_date"] = _iso_date(to_date)
        if direction:
            filters["direction"] = direction
        account = await banking.get_account(account_number)
        rows = await banking.list_transactions(account_number, **filters)
        return ToolOutput(
            data={
                "account_number": account_number,
                "currency": account.get("currency"),
                "transactions": [{k: row.get(k) for k in TRANSACTION_FIELDS} for row in rows],
            },
            citations=(Citation("record", "Account", account_number),),
            record=account,
        )

    @server.tool(
        "get_status",
        "Status of one transaction or transfer by its reference, with the reason if it failed.",
    )
    async def get_status(caller: Caller, reference: str) -> ToolOutput:
        transaction = await banking.get_transaction(reference.strip().upper())
        account = await banking.get_account(transaction["account_number"])
        return ToolOutput(
            data={
                **{k: transaction.get(k) for k in TRANSACTION_FIELDS},
                "failure_code": transaction.get("failure_code"),
                "failure_reason": transaction.get("failure_reason"),
            },
            citations=(Citation("record", "Transaction", transaction["reference"]),),
            record=account,
        )

    return server


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise ToolInputError(f"{value!r} is not a date; use YYYY-MM-DD") from None
