"""Real lending client: loans, their schedules, and term deposits.

PROVISIONAL: the bank has not yet said what its lending system exposes, so this client speaks a
plain REST interface of our own (served for development by `packs/banking/mock_bank.py`):

    GET /customers/{customer_number}/loans
    GET /loans/{loan_id}
    GET /loans/{loan_id}/schedule
    GET /customers/{customer_number}/deposits
    GET /deposits/{deposit_id}

When the bank's interface is known, change the paths in the methods and the `to_*` functions
that map its responses to the records in `base.py`. Nothing outside this file needs to change;
`tests/test_adapter_contract.py` shows whether the result still keeps the contract.
"""

from typing import Any

from packs.banking.adapters.base import Deposit, Instalment, Loan
from packs.banking.adapters.http import (
    BankHttp,
    iso_date,
    mapped,
    money,
    one_of,
    optional_date,
    optional_money,
    segment,
)


class HttpLendingClient:
    def __init__(self, http: BankHttp):
        self.http = http

    async def list_loans(self, customer_number: str) -> list[Loan]:
        raw = await self.http.get(f"/customers/{segment(customer_number)}/loans")
        return mapped(lambda items: [to_loan(r) for r in items], raw, "loan list")

    async def get_loan(self, loan_id: str) -> Loan:
        raw = await self.http.get(f"/loans/{segment(loan_id)}")
        return mapped(to_loan, raw, "loan")

    async def get_schedule(self, loan_id: str) -> list[Instalment]:
        raw = await self.http.get(f"/loans/{segment(loan_id)}/schedule")
        rows = mapped(lambda items: [to_instalment(r) for r in items], raw, "schedule")
        return sorted(rows, key=lambda r: r["due_date"])

    async def list_deposits(self, customer_number: str) -> list[Deposit]:
        raw = await self.http.get(f"/customers/{segment(customer_number)}/deposits")
        return mapped(lambda items: [to_deposit(r) for r in items], raw, "deposit list")

    async def get_deposit(self, deposit_id: str) -> Deposit:
        raw = await self.http.get(f"/deposits/{segment(deposit_id)}")
        return mapped(to_deposit, raw, "deposit")


LOAN_STATUSES = ("pending_disbursement", "current", "in_arrears", "restructured", "closed")


def to_loan(raw: dict[str, Any]) -> Loan:
    return {
        "loan_id": str(raw["loan_id"]).upper(),
        "customer_number": str(raw["customer_number"]),
        "branch": str(raw["branch"]).upper(),
        "product": str(raw["product"]),
        "currency": str(raw["currency"]).upper(),
        "principal": money(raw["principal"]),
        "outstanding": money(raw["outstanding"]),
        "rate": f"{float(raw['rate']):.1f}",
        "start_date": iso_date(raw["start_date"]),
        "maturity_date": iso_date(raw["maturity_date"]),
        "repayment_account": str(raw["repayment_account"]),
        "next_due_date": optional_date(raw.get("next_due_date")),
        "next_due_amount": optional_money(raw.get("next_due_amount")),
        "arrears_amount": money(raw.get("arrears_amount") or 0),
        "days_past_due": int(raw.get("days_past_due") or 0),
        "status": one_of(raw["status"], LOAN_STATUSES),
    }


def to_instalment(raw: dict[str, Any]) -> Instalment:
    return {
        "due_date": iso_date(raw["due_date"]),
        "amount": money(raw["amount"]),
        "principal": money(raw["principal"]),
        "interest": money(raw["interest"]),
        "paid": money(raw.get("paid") or 0),
        "status": one_of(raw["status"], ("paid", "partly_paid", "overdue", "due")),
    }


def to_deposit(raw: dict[str, Any]) -> Deposit:
    return {
        "deposit_id": str(raw["deposit_id"]).upper(),
        "customer_number": str(raw["customer_number"]),
        "branch": str(raw["branch"]).upper(),
        "product": str(raw["product"]),
        "currency": str(raw["currency"]).upper(),
        "principal": money(raw["principal"]),
        "rate": f"{float(raw['rate']):.1f}",
        "start_date": iso_date(raw["start_date"]),
        "maturity_date": iso_date(raw["maturity_date"]),
        "maturity_amount": money(raw["maturity_amount"]),
        "rollover": one_of(raw["rollover"], ("none", "principal", "principal_and_interest")),
        "early_withdrawal_penalty": str(raw.get("early_withdrawal_penalty") or ""),
        "status": one_of(raw["status"], ("running", "matured", "closed")),
    }
