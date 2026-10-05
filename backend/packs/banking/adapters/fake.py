"""In-memory fakes with seed data. Used by development, tests and evals."""

import re
from typing import Any

from packs.banking.adapters.base import NotFound

CUSTOMERS = {
    "C1001": {"customer_number": "C1001", "name": "Ama Mensah", "branch": "ACC-01", "flags": []},
    "C1002": {
        "customer_number": "C1002",
        "name": "Kofi Asante",
        "branch": "KSI-02",
        "flags": ["kyc_review_due"],
    },
}
ACCOUNTS = {
    "0011223344": {
        "account_number": "0011223344",
        "customer_number": "C1001",
        "branch": "ACC-01",
        "type": "current",
        "currency": "GHS",
        "balance": "4520.75",
        "status": "active",
    },
    "0011223355": {
        "account_number": "0011223355",
        "customer_number": "C1001",
        "branch": "ACC-01",
        "type": "savings",
        "currency": "GHS",
        "balance": "1500.50",
        "status": "active",
    },
    "0099887766": {
        "account_number": "0099887766",
        "customer_number": "C1002",
        "branch": "KSI-02",
        "type": "savings",
        "currency": "GHS",
        "balance": "12800.00",
        "status": "dormant",
    },
}
TRANSACTIONS = [
    {
        "reference": "TX-0001",
        "account_number": "0011223344",
        "date": "2026-09-28",
        "amount": "-250.00",
        "direction": "debit",
        "narration": "ATM withdrawal",
        "status": "completed",
        "failure_code": None,
        "failure_reason": None,
    },
    {
        "reference": "TX-0002",
        "account_number": "0011223344",
        "date": "2026-09-30",
        "amount": "-1200.00",
        "direction": "debit",
        "narration": "Transfer to 5566778899",
        "status": "failed",
        "failure_code": "E51",
        "failure_reason": "Beneficiary account closed",
    },
    {
        "reference": "TX-0003",
        "account_number": "0011223344",
        "date": "2026-10-01",
        "amount": "3000.00",
        "direction": "credit",
        "narration": "Salary",
        "status": "completed",
        "failure_code": None,
        "failure_reason": None,
    },
    {
        "reference": "TX-0004",
        "account_number": "0011223355",
        "date": "2026-09-15",
        "amount": "500.00",
        "direction": "credit",
        "narration": "Transfer from current account",
        "status": "completed",
        "failure_code": None,
        "failure_reason": None,
    },
    {
        "reference": "TX-0005",
        "account_number": "0099887766",
        "date": "2025-01-10",
        "amount": "-40.00",
        "direction": "debit",
        "narration": "Account maintenance fee",
        "status": "completed",
        "failure_code": None,
        "failure_reason": None,
    },
]
PRODUCTS = {
    "SAV-STD": {
        "code": "SAV-STD",
        "name": "Standard Savings",
        "rate": "8.5%",
        "fees": {"monthly": "0.00"},
        "eligibility": "Individuals 18 and over",
        "required_documents": ["valid ID", "proof of address"],
    },
    "CUR-BIZ": {
        "code": "CUR-BIZ",
        "name": "Business Current",
        "rate": "0%",
        "fees": {"monthly": "25.00"},
        "eligibility": "Registered businesses",
        "required_documents": ["certificate of incorporation", "director IDs"],
    },
}
REQUIREMENTS = {
    "joint_account_opening": {
        "request_type": "joint_account_opening",
        "forms": ["Account opening form", "Joint mandate form"],
        "signatures": ["All account holders"],
        "approvals": ["Customer service supervisor"],
    },
}
OPEN_REQUESTS = {
    "C1001": [{"id": "REQ-77", "type": "card_replacement", "status": "in_progress"}],
}


class FakeCoreBanking:
    async def get_account(self, account_number: str) -> dict[str, Any]:
        if account_number not in ACCOUNTS:
            raise NotFound(account_number)
        return dict(ACCOUNTS[account_number])

    async def list_transactions(self, account_number: str, **filters: Any) -> list[dict[str, Any]]:
        if account_number not in ACCOUNTS:
            raise NotFound(account_number)
        rows = [t for t in TRANSACTIONS if t["account_number"] == account_number]
        if direction := filters.get("direction"):
            rows = [t for t in rows if t["direction"] == direction]
        if from_date := filters.get("from_date"):
            rows = [t for t in rows if t["date"] >= from_date]
        if to_date := filters.get("to_date"):
            rows = [t for t in rows if t["date"] <= to_date]
        rows.sort(key=lambda t: t["date"], reverse=True)
        return [dict(t) for t in rows[: filters.get("limit", 5)]]

    async def get_transaction(self, reference: str) -> dict[str, Any]:
        for t in TRANSACTIONS:
            if t["reference"] == reference:
                return dict(t)
        raise NotFound(reference)

    async def get_customer(self, customer_number: str) -> dict[str, Any]:
        if customer_number not in CUSTOMERS:
            raise NotFound(customer_number)
        customer = dict(CUSTOMERS[customer_number])
        customer["accounts"] = [
            a["account_number"]
            for a in ACCOUNTS.values()
            if a["customer_number"] == customer_number
        ]
        return customer


class FakeServiceCatalog:
    async def search_products(self, query: str) -> list[dict[str, Any]]:
        """Products sharing a word with the query, best match first, as a catalogue search would:
        "Business Current account" finds Business Current."""
        words = set(re.findall(r"[a-z0-9]+", query.lower())) - {"account", "the", "a"}
        scored = []
        for p in PRODUCTS.values():
            names = set(re.findall(r"[a-z0-9]+", f"{p['name']} {p['code']}".lower()))
            if overlap := len(words & names):
                scored.append((overlap, p))
        scored.sort(key=lambda item: -item[0])
        return [{"code": p["code"], "name": p["name"]} for _, p in scored]

    async def get_product(self, code: str) -> dict[str, Any]:
        if code not in PRODUCTS:
            raise NotFound(code)
        return dict(PRODUCTS[code])

    async def get_requirements(self, request_type: str) -> dict[str, Any]:
        if request_type not in REQUIREMENTS:
            raise NotFound(request_type)
        return dict(REQUIREMENTS[request_type])

    async def open_requests(self, customer_number: str) -> list[dict[str, Any]]:
        return [dict(r) for r in OPEN_REQUESTS.get(customer_number, [])]
