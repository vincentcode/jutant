"""Real core banking client.

PROVISIONAL: the bank has not yet said what its core system exposes, so this client speaks a
plain REST interface of our own (served for development by `packs/banking/mock_bank.py`):

    GET /accounts/{account_number}
    GET /accounts/{account_number}/transactions?from_date=&to_date=&direction=&limit=
    GET /transactions/{reference}
    GET /customers/{customer_number}

When the bank's interface is known, change the paths in the methods and the `to_*` functions
that map its responses to the records in `base.py`. Nothing outside this file needs to change;
`tests/test_adapter_contract.py` shows whether the result still keeps the contract.
"""

from typing import Any

from packs.banking.adapters.base import Account, Customer, Transaction
from packs.banking.adapters.http import BankHttp, iso_date, mapped, money, optional, segment

DEFAULT_LIMIT = 5


class HttpCoreBankingClient:
    def __init__(self, http: BankHttp):
        self.http = http

    async def get_account(self, account_number: str) -> Account:
        raw = await self.http.get(f"/accounts/{segment(account_number)}")
        return mapped(to_account, raw, "account")

    async def list_transactions(self, account_number: str, **filters: Any) -> list[Transaction]:
        limit = filters.get("limit", DEFAULT_LIMIT)
        raw = await self.http.get(
            f"/accounts/{segment(account_number)}/transactions",
            {
                "from_date": filters.get("from_date"),
                "to_date": filters.get("to_date"),
                "direction": filters.get("direction"),
                "limit": limit,
            },
        )
        rows = mapped(lambda items: [to_transaction(r) for r in items], raw, "transaction list")
        # Kept here too, in case the bank's system ignores a filter or its order differs.
        rows = [r for r in rows if _within(r, filters)]
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows[:limit]

    async def get_transaction(self, reference: str) -> Transaction:
        raw = await self.http.get(f"/transactions/{segment(reference)}")
        return mapped(to_transaction, raw, "transaction")

    async def get_customer(self, customer_number: str) -> Customer:
        raw = await self.http.get(f"/customers/{segment(customer_number)}")
        return mapped(to_customer, raw, "customer")


def to_account(raw: dict[str, Any]) -> Account:
    return {
        "account_number": str(raw["account_number"]),
        "customer_number": str(raw["customer_number"]),
        "branch": str(raw["branch"]).upper(),
        "type": str(raw["type"]).lower(),
        "currency": str(raw["currency"]).upper(),
        "balance": money(raw["balance"]),
        "status": _one_of(raw["status"], ("active", "dormant", "closed", "blocked")),
    }


def to_transaction(raw: dict[str, Any]) -> Transaction:
    direction = _one_of(raw["direction"], ("debit", "credit"))
    amount = money(raw["amount"])
    if direction == "debit" and not amount.startswith("-"):
        amount = f"-{amount}"  # debits are negative, whichever way the bank signs them
    return {
        "reference": str(raw["reference"]).upper(),
        "account_number": str(raw["account_number"]),
        "date": iso_date(raw["date"]),
        "amount": amount,
        "direction": direction,
        "narration": str(raw.get("narration") or ""),
        "status": _one_of(raw["status"], ("completed", "pending", "failed", "reversed")),
        "failure_code": optional(raw.get("failure_code")),
        "failure_reason": optional(raw.get("failure_reason")),
    }


def to_customer(raw: dict[str, Any]) -> Customer:
    return {
        "customer_number": str(raw["customer_number"]),
        "name": str(raw["name"]),
        "branch": str(raw["branch"]).upper(),
        "flags": [str(f) for f in raw.get("flags") or []],
        "accounts": [str(a) for a in raw.get("accounts") or []],
    }


def _one_of(value: Any, allowed: tuple[str, ...]) -> Any:
    text = str(value).lower()
    if text not in allowed:
        raise ValueError(f"{value!r} is not one of {', '.join(allowed)}")
    return text


def _within(row: Transaction, filters: dict[str, Any]) -> bool:
    if (direction := filters.get("direction")) and row["direction"] != direction:
        return False
    if (start := filters.get("from_date")) and row["date"] < start:
        return False
    return not ((end := filters.get("to_date")) and row["date"] > end)
