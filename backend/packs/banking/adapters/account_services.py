"""Real account services and customer records clients.

PROVISIONAL: the bank has not yet said what its systems expose (usually its core banking
system), so these clients speak a plain REST interface of our own (served for development by
`packs/banking/mock_bank.py`):

    GET /accounts/{account_number}/status
    GET /accounts/{account_number}/mandate
    GET /accounts/{account_number}/charges?from_date=&to_date=&limit=
    GET /accounts/{account_number}/standing-orders
    GET /accounts/{account_number}/cheques/{cheque_number}
    GET /customers/{customer_number}/kyc

When the bank's interface is known, change the paths in the methods and the `to_*` functions
that map its responses to the records in `base.py`. Nothing outside this file needs to change;
`tests/test_adapter_contract.py` shows whether the result still keeps the contract.
"""

from typing import Any

from packs.banking.adapters.base import (
    AccountStatus,
    Charge,
    Cheque,
    Hold,
    Kyc,
    Mandate,
    StandingOrder,
)
from packs.banking.adapters.http import (
    BankHttp,
    flag,
    iso_date,
    mapped,
    money,
    one_of,
    optional,
    optional_date,
    optional_money,
    segment,
)

DEFAULT_CHARGES = 10


class HttpAccountServicesClient:
    def __init__(self, http: BankHttp):
        self.http = http

    async def get_status(self, account_number: str) -> AccountStatus:
        raw = await self.http.get(f"/accounts/{segment(account_number)}/status")
        return mapped(to_status, raw, "account status")

    async def get_mandate(self, account_number: str) -> Mandate:
        raw = await self.http.get(f"/accounts/{segment(account_number)}/mandate")
        return mapped(to_mandate, raw, "mandate")

    async def list_charges(self, account_number: str, **filters: Any) -> list[Charge]:
        limit = filters.get("limit", DEFAULT_CHARGES)
        raw = await self.http.get(
            f"/accounts/{segment(account_number)}/charges",
            {
                "from_date": filters.get("from_date"),
                "to_date": filters.get("to_date"),
                "limit": limit,
            },
        )
        rows = mapped(lambda items: [to_charge(c) for c in items], raw, "charge list")
        rows.sort(key=lambda c: c["date"], reverse=True)
        return rows[:limit]

    async def list_standing_orders(self, account_number: str) -> list[StandingOrder]:
        raw = await self.http.get(f"/accounts/{segment(account_number)}/standing-orders")
        return mapped(lambda items: [to_standing_order(o) for o in items], raw, "standing orders")

    async def get_cheque(self, account_number: str, cheque_number: str) -> Cheque:
        raw = await self.http.get(
            f"/accounts/{segment(account_number)}/cheques/{segment(cheque_number)}"
        )
        return mapped(to_cheque, raw, "cheque")


class HttpCustomerRecordsClient:
    def __init__(self, http: BankHttp):
        self.http = http

    async def get_kyc(self, customer_number: str) -> Kyc:
        raw = await self.http.get(f"/customers/{segment(customer_number)}/kyc")
        return mapped(to_kyc, raw, "KYC record")


def to_hold(raw: dict[str, Any]) -> Hold:
    return {
        "id": str(raw["id"]),
        "type": one_of(raw["type"], ("lien", "block", "garnishment", "uncleared_funds", "other")),
        "amount": optional_money(raw.get("amount")),
        "reason": str(raw.get("reason") or ""),
        "placed_on": iso_date(raw["placed_on"]),
        "expires_on": optional_date(raw.get("expires_on")),
        "placed_by": str(raw.get("placed_by") or ""),
    }


def to_status(raw: dict[str, Any]) -> AccountStatus:
    return {
        "account_number": str(raw["account_number"]),
        "branch": str(raw["branch"]).upper(),
        "status": one_of(raw["status"], ("active", "dormant", "closed", "blocked")),
        "currency": str(raw["currency"]).upper(),
        "ledger_balance": money(raw["ledger_balance"]),
        "available_balance": money(raw["available_balance"]),
        "debits_blocked": flag(raw.get("debits_blocked")),
        "credits_blocked": flag(raw.get("credits_blocked")),
        "dormant_since": optional_date(raw.get("dormant_since")),
        "holds": [to_hold(h) for h in raw.get("holds") or []],
        "daily_withdrawal_limit": money(raw["daily_withdrawal_limit"]),
        "overdraft_limit": money(raw.get("overdraft_limit") or 0),
    }


def to_mandate(raw: dict[str, Any]) -> Mandate:
    return {
        "account_number": str(raw["account_number"]),
        "rule": str(raw["rule"]),
        "signatories": [
            {
                "customer_number": str(s["customer_number"]),
                "name": str(s["name"]),
                "role": one_of(s["role"], ("primary", "joint", "authorised")),
            }
            for s in raw.get("signatories") or []
        ],
    }


def to_charge(raw: dict[str, Any]) -> Charge:
    amount = money(raw["amount"])
    return {
        "reference": str(raw["reference"]).upper(),
        "account_number": str(raw["account_number"]),
        "date": iso_date(raw["date"]),
        "amount": amount if amount.startswith("-") else f"-{amount}",  # always taken
        "fee_code": str(raw["fee_code"]).upper(),
        "description": str(raw.get("description") or ""),
    }


def to_standing_order(raw: dict[str, Any]) -> StandingOrder:
    last = raw.get("last_result")
    return {
        "id": str(raw["id"]).upper(),
        "account_number": str(raw["account_number"]),
        "beneficiary": str(raw["beneficiary"]),
        "amount": money(raw["amount"]),
        "frequency": one_of(raw["frequency"], ("weekly", "monthly", "quarterly", "yearly")),
        "next_run": optional_date(raw.get("next_run")),
        "last_run": optional_date(raw.get("last_run")),
        "last_result": one_of(last, ("paid", "failed")) if last else None,
        "failure_reason": optional(raw.get("failure_reason")),
        "status": one_of(raw["status"], ("active", "suspended", "ended")),
    }


def to_cheque(raw: dict[str, Any]) -> Cheque:
    return {
        "account_number": str(raw["account_number"]),
        "cheque_number": str(raw["cheque_number"]),
        "status": one_of(raw["status"], ("unused", "in_clearing", "paid", "returned", "stopped")),
        "amount": optional_money(raw.get("amount")),
        "payee": optional(raw.get("payee")),
        "presented_on": optional_date(raw.get("presented_on")),
        "return_code": optional(raw.get("return_code")),
        "return_reason": optional(raw.get("return_reason")),
    }


def to_kyc(raw: dict[str, Any]) -> Kyc:
    return {
        "customer_number": str(raw["customer_number"]),
        "status": one_of(raw["status"], ("verified", "review_due", "expired", "incomplete")),
        "risk_rating": one_of(raw["risk_rating"], ("low", "medium", "high")),
        "last_review": optional_date(raw.get("last_review")),
        "next_review": optional_date(raw.get("next_review")),
        "id_type": optional(raw.get("id_type")),
        "id_expiry": optional_date(raw.get("id_expiry")),
        "missing_documents": [str(d) for d in raw.get("missing_documents") or []],
    }
