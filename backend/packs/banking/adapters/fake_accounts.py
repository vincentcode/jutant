"""In-memory account services and customer records, with seed data for the fake bank's accounts.

The data tells stories staff ask about:

- 0011223344 (Ama Mensah): active, but a loan lien and an uncleared cheque deposit hold part of
  the balance, so her rent standing order failed on 1 October; a cheque of hers was returned
  for insufficient funds, and the returned-cheque fee charged.
- 0011223355 (Ama and Yaw Mensah): a joint savings account; both must sign.
- 0099887766 (Kofi Asante): dormant, so nothing may leave it; his KYC review is overdue.
"""

from typing import Any

from packs.banking.adapters.base import NotFound

STATUS: dict[str, dict[str, Any]] = {
    "0011223344": {
        "account_number": "0011223344",
        "branch": "ACC-01",
        "status": "active",
        "currency": "GHS",
        "ledger_balance": "4520.75",
        "available_balance": "2220.75",
        "debits_blocked": False,
        "credits_blocked": False,
        "dormant_since": None,
        "holds": [
            {
                "id": "H-501",
                "type": "lien",
                "amount": "1500.00",
                "reason": "Security for loan LN-1001",
                "placed_on": "2025-10-15",
                "expires_on": "2027-10-15",
                "placed_by": "Credit",
            },
            {
                "id": "H-502",
                "type": "uncleared_funds",
                "amount": "800.00",
                "reason": "Cheque deposit awaiting clearing",
                "placed_on": "2026-09-30",
                "expires_on": "2026-10-03",
                "placed_by": "Clearing",
            },
        ],
        "daily_withdrawal_limit": "5000.00",
        "overdraft_limit": "0.00",
    },
    "0011223355": {
        "account_number": "0011223355",
        "branch": "ACC-01",
        "status": "active",
        "currency": "GHS",
        "ledger_balance": "1500.50",
        "available_balance": "1500.50",
        "debits_blocked": False,
        "credits_blocked": False,
        "dormant_since": None,
        "holds": [],
        "daily_withdrawal_limit": "2000.00",
        "overdraft_limit": "0.00",
    },
    "0099887766": {
        "account_number": "0099887766",
        "branch": "KSI-02",
        "status": "dormant",
        "currency": "GHS",
        "ledger_balance": "12800.00",
        "available_balance": "0.00",
        "debits_blocked": True,
        "credits_blocked": False,
        "dormant_since": "2025-04-10",
        "holds": [
            {
                "id": "H-610",
                "type": "block",
                "amount": None,
                "reason": "Dormant account: no customer-initiated activity for 12 months",
                "placed_on": "2025-04-10",
                "expires_on": None,
                "placed_by": "Operations",
            }
        ],
        "daily_withdrawal_limit": "2000.00",
        "overdraft_limit": "0.00",
    },
}
MANDATES: dict[str, dict[str, Any]] = {
    "0011223344": {
        "account_number": "0011223344",
        "rule": "sole signatory",
        "signatories": [{"customer_number": "C1001", "name": "Ama Mensah", "role": "primary"}],
    },
    "0011223355": {
        "account_number": "0011223355",
        "rule": "both to sign",
        "signatories": [
            {"customer_number": "C1001", "name": "Ama Mensah", "role": "joint"},
            {"customer_number": "C1003", "name": "Yaw Mensah", "role": "joint"},
        ],
    },
    "0099887766": {
        "account_number": "0099887766",
        "rule": "sole signatory",
        "signatories": [{"customer_number": "C1002", "name": "Kofi Asante", "role": "primary"}],
    },
}
CHARGES = [
    {
        "reference": "CH-9001",
        "account_number": "0011223344",
        "date": "2026-09-30",
        "amount": "-10.00",
        "fee_code": "F01",
        "description": "Monthly account maintenance",
    },
    {
        "reference": "CH-9002",
        "account_number": "0011223344",
        "date": "2026-09-30",
        "amount": "-2.50",
        "fee_code": "F07",
        "description": "SMS alerts, September",
    },
    {
        "reference": "CH-9003",
        "account_number": "0011223344",
        "date": "2026-10-03",
        "amount": "-50.00",
        "fee_code": "F12",
        "description": "Returned cheque 000102",
    },
    {
        "reference": "CH-9004",
        "account_number": "0099887766",
        "date": "2025-01-10",
        "amount": "-40.00",
        "fee_code": "F01",
        "description": "Account maintenance",
    },
]
STANDING_ORDERS = [
    {
        "id": "SO-301",
        "account_number": "0011223344",
        "beneficiary": "Mensah Rent Ltd",
        "amount": "2500.00",
        "frequency": "monthly",
        "next_run": "2026-11-01",
        "last_run": "2026-10-01",
        "last_result": "failed",
        "failure_reason": "Insufficient available balance",
        "status": "active",
    },
    {
        "id": "SO-302",
        "account_number": "0011223344",
        "beneficiary": "Ama Mensah savings 0011223355",
        "amount": "200.00",
        "frequency": "monthly",
        "next_run": "2026-10-25",
        "last_run": "2026-09-25",
        "last_result": "paid",
        "failure_reason": None,
        "status": "active",
    },
]
CHEQUES = [
    {
        "account_number": "0011223344",
        "cheque_number": "000101",
        "status": "paid",
        "amount": "350.00",
        "payee": "Electricity Company of Ghana",
        "presented_on": "2026-09-20",
        "return_code": None,
        "return_reason": None,
    },
    {
        "account_number": "0011223344",
        "cheque_number": "000102",
        "status": "returned",
        "amount": "3000.00",
        "payee": "Kwame Boateng",
        "presented_on": "2026-10-02",
        "return_code": "R01",
        "return_reason": "Insufficient funds",
    },
    {
        "account_number": "0011223344",
        "cheque_number": "000103",
        "status": "stopped",
        "amount": None,
        "payee": None,
        "presented_on": None,
        "return_code": None,
        "return_reason": None,
    },
    {
        "account_number": "0011223344",
        "cheque_number": "000104",
        "status": "in_clearing",
        "amount": "120.00",
        "payee": "Accra Water",
        "presented_on": "2026-10-11",
        "return_code": None,
        "return_reason": None,
    },
]
KYC = {
    "C1001": {
        "customer_number": "C1001",
        "status": "verified",
        "risk_rating": "low",
        "last_review": "2025-03-01",
        "next_review": "2027-03-01",
        "id_type": "Ghana Card",
        "id_expiry": "2029-06-30",
        "missing_documents": [],
    },
    "C1002": {
        "customer_number": "C1002",
        "status": "review_due",
        "risk_rating": "medium",
        "last_review": "2023-09-01",
        "next_review": "2026-09-01",
        "id_type": "Passport",
        "id_expiry": "2026-11-15",
        "missing_documents": ["proof of address"],
    },
}
DEFAULT_CHARGES = 10


class FakeAccountServices:
    async def get_status(self, account_number: str) -> dict[str, Any]:
        if account_number not in STATUS:
            raise NotFound(account_number)
        status = dict(STATUS[account_number])
        status["holds"] = [dict(h) for h in status["holds"]]
        return status

    async def get_mandate(self, account_number: str) -> dict[str, Any]:
        if account_number not in MANDATES:
            raise NotFound(account_number)
        mandate = dict(MANDATES[account_number])
        mandate["signatories"] = [dict(s) for s in mandate["signatories"]]
        return mandate

    async def list_charges(self, account_number: str, **filters: Any) -> list[dict[str, Any]]:
        if account_number not in STATUS:
            raise NotFound(account_number)
        rows = [c for c in CHARGES if c["account_number"] == account_number]
        if from_date := filters.get("from_date"):
            rows = [c for c in rows if c["date"] >= from_date]
        if to_date := filters.get("to_date"):
            rows = [c for c in rows if c["date"] <= to_date]
        rows.sort(key=lambda c: (c["date"], c["reference"]), reverse=True)
        return [dict(c) for c in rows[: filters.get("limit", DEFAULT_CHARGES)]]

    async def list_standing_orders(self, account_number: str) -> list[dict[str, Any]]:
        if account_number not in STATUS:
            raise NotFound(account_number)
        return [dict(o) for o in STANDING_ORDERS if o["account_number"] == account_number]

    async def get_cheque(self, account_number: str, cheque_number: str) -> dict[str, Any]:
        for cheque in CHEQUES:
            if (cheque["account_number"], cheque["cheque_number"]) == (
                account_number,
                cheque_number,
            ):
                return dict(cheque)
        raise NotFound(f"{account_number}/{cheque_number}")


class FakeCustomerRecords:
    async def get_kyc(self, customer_number: str) -> dict[str, Any]:
        if customer_number not in KYC:
            raise NotFound(customer_number)
        kyc = dict(KYC[customer_number])
        kyc["missing_documents"] = list(kyc["missing_documents"])
        return kyc
