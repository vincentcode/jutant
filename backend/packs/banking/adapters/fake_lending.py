"""In-memory lending system, with seed data for the fake bank's customers.

- LN-1001 (Ama Mensah): a personal loan, up to date; its lien sits on her current account.
- LN-1002 (Kofi Asante): a business loan two instalments in arrears; its repayment account is
  the dormant 0099887766, so repayments cannot be taken from it.
- LN-1003 (Ama Mensah): approved, awaiting disbursement.
- FD-2001 (Ama Mensah): a fixed deposit running to January, rolled over with its interest.
- FD-2002 (Kofi Asante): a fixed deposit that matured on 30 September and is not rolled over.
"""

from typing import Any

from packs.banking.adapters.base import NotFound

LOANS: dict[str, dict[str, Any]] = {
    "LN-1001": {
        "loan_id": "LN-1001",
        "customer_number": "C1001",
        "branch": "ACC-01",
        "product": "Personal loan",
        "currency": "GHS",
        "principal": "20000.00",
        "outstanding": "12450.00",
        "rate": "24.0",
        "start_date": "2025-10-15",
        "maturity_date": "2027-10-15",
        "repayment_account": "0011223344",
        "next_due_date": "2026-10-15",
        "next_due_amount": "1057.50",
        "arrears_amount": "0.00",
        "days_past_due": 0,
        "status": "current",
    },
    "LN-1002": {
        "loan_id": "LN-1002",
        "customer_number": "C1002",
        "branch": "KSI-02",
        "product": "SME working capital loan",
        "currency": "GHS",
        "principal": "50000.00",
        "outstanding": "41200.00",
        "rate": "28.0",
        "start_date": "2025-12-25",
        "maturity_date": "2027-12-25",
        "repayment_account": "0099887766",
        "next_due_date": "2026-10-25",
        "next_due_amount": "2115.00",
        "arrears_amount": "4230.00",
        "days_past_due": 47,
        "status": "in_arrears",
    },
    "LN-1003": {
        "loan_id": "LN-1003",
        "customer_number": "C1001",
        "branch": "ACC-01",
        "product": "Salary advance",
        "currency": "GHS",
        "principal": "5000.00",
        "outstanding": "0.00",
        "rate": "30.0",
        "start_date": "2026-10-10",
        "maturity_date": "2027-04-10",
        "repayment_account": "0011223344",
        "next_due_date": None,
        "next_due_amount": None,
        "arrears_amount": "0.00",
        "days_past_due": 0,
        "status": "pending_disbursement",
    },
}


def _instalment(due: str, amount: str, principal: str, interest: str, paid: str, status: str):
    return {
        "due_date": due,
        "amount": amount,
        "principal": principal,
        "interest": interest,
        "paid": paid,
        "status": status,
    }


SCHEDULES: dict[str, list[dict[str, Any]]] = {
    "LN-1001": [
        _instalment("2026-08-15", "1057.50", "808.50", "249.00", "1057.50", "paid"),
        _instalment("2026-09-15", "1057.50", "824.67", "232.83", "1057.50", "paid"),
        _instalment("2026-10-15", "1057.50", "841.16", "216.34", "0.00", "due"),
        _instalment("2026-11-15", "1057.50", "857.98", "199.52", "0.00", "due"),
    ],
    "LN-1002": [
        _instalment("2026-07-25", "2115.00", "1150.00", "965.00", "2115.00", "paid"),
        _instalment("2026-08-25", "2115.00", "1176.83", "938.17", "0.00", "overdue"),
        _instalment("2026-09-25", "2115.00", "1204.29", "910.71", "0.00", "overdue"),
        _instalment("2026-10-25", "2115.00", "1232.39", "882.61", "0.00", "due"),
    ],
    "LN-1003": [],
}
DEPOSITS: dict[str, dict[str, Any]] = {
    "FD-2001": {
        "deposit_id": "FD-2001",
        "customer_number": "C1001",
        "branch": "ACC-01",
        "product": "Fixed deposit, 6 months",
        "currency": "GHS",
        "principal": "10000.00",
        "rate": "18.0",
        "start_date": "2026-07-01",
        "maturity_date": "2027-01-01",
        "maturity_amount": "10900.00",
        "rollover": "principal_and_interest",
        "early_withdrawal_penalty": "2% of principal",
        "status": "running",
    },
    "FD-2002": {
        "deposit_id": "FD-2002",
        "customer_number": "C1002",
        "branch": "KSI-02",
        "product": "Fixed deposit, 3 months",
        "currency": "GHS",
        "principal": "5000.00",
        "rate": "24.8",
        "start_date": "2026-06-30",
        "maturity_date": "2026-09-30",
        "maturity_amount": "5310.00",
        "rollover": "none",
        "early_withdrawal_penalty": "2% of principal",
        "status": "matured",
    },
}


class FakeLending:
    async def list_loans(self, customer_number: str) -> list[dict[str, Any]]:
        return [dict(loan) for loan in LOANS.values() if loan["customer_number"] == customer_number]

    async def get_loan(self, loan_id: str) -> dict[str, Any]:
        if loan_id not in LOANS:
            raise NotFound(loan_id)
        return dict(LOANS[loan_id])

    async def get_schedule(self, loan_id: str) -> list[dict[str, Any]]:
        if loan_id not in SCHEDULES:
            raise NotFound(loan_id)
        return [dict(i) for i in SCHEDULES[loan_id]]

    async def list_deposits(self, customer_number: str) -> list[dict[str, Any]]:
        return [dict(d) for d in DEPOSITS.values() if d["customer_number"] == customer_number]

    async def get_deposit(self, deposit_id: str) -> dict[str, Any]:
        if deposit_id not in DEPOSITS:
            raise NotFound(deposit_id)
        return dict(DEPOSITS[deposit_id])
