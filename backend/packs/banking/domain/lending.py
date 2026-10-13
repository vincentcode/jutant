"""Loans and deposits, set out for staff: arrears, what is overdue, what a deposit earns.

Every figure is computed here, with decimal arithmetic, from the lending system's own numbers:
the model words them, and never adds anything up itself.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from packs.banking.adapters.base import Deposit, Instalment, Loan

LOAN_STATUS = {
    "pending_disbursement": "approved, not yet disbursed",
    "current": "up to date",
    "in_arrears": "in arrears",
    "restructured": "restructured",
    "closed": "closed",
}


def loan(record: Loan, schedule: list[Instalment]) -> dict[str, Any]:
    """The loan, with its overdue instalments and what has been repaid."""
    overdue = [i for i in schedule if i["status"] in ("overdue", "partly_paid")]
    owed = sum((Decimal(i["amount"]) - Decimal(i["paid"]) for i in overdue), Decimal(0))
    repaid = Decimal(record["principal"]) - Decimal(record["outstanding"])
    upcoming = [i for i in schedule if i["status"] == "due"][:3]
    return {
        **record,
        "status_in_words": LOAN_STATUS[record["status"]],
        "principal_repaid": f"{max(repaid, Decimal(0)):.2f}"
        if record["status"] != "pending_disbursement"
        else "0.00",
        "overdue_instalments": len(overdue),
        "overdue_amount": f"{owed:.2f}",
        "oldest_overdue": overdue[0]["due_date"] if overdue else None,
        "upcoming": upcoming,
    }


def deposit(record: Deposit, today: date | None = None) -> dict[str, Any]:
    """The deposit, with the interest it earns at maturity and the days left."""
    left = (date.fromisoformat(record["maturity_date"]) - (today or date.today())).days
    interest = Decimal(record["maturity_amount"]) - Decimal(record["principal"])
    return {
        **record,
        "interest_at_maturity": f"{interest:.2f}",
        "days_to_maturity": max(left, 0),
        "matured": left <= 0,
    }


def facilities(loans: list[Loan], deposits: list[Deposit]) -> dict[str, Any]:
    """A customer's loans and deposits, with their totals by currency."""
    outstanding: dict[str, Decimal] = {}
    arrears: dict[str, Decimal] = {}
    deposited: dict[str, Decimal] = {}
    for item in loans:
        if item["status"] != "closed":
            cur = item["currency"]
            outstanding[cur] = outstanding.get(cur, Decimal(0)) + Decimal(item["outstanding"])
            arrears[cur] = arrears.get(cur, Decimal(0)) + Decimal(item["arrears_amount"])
    for item in deposits:
        if item["status"] != "closed":
            cur = item["currency"]
            deposited[cur] = deposited.get(cur, Decimal(0)) + Decimal(item["principal"])
    return {
        "loans": [
            {
                k: item[k]  # type: ignore[literal-required]
                for k in (
                    "loan_id",
                    "product",
                    "currency",
                    "outstanding",
                    "arrears_amount",
                    "days_past_due",
                    "next_due_date",
                    "next_due_amount",
                    "status",
                )
            }
            for item in loans
        ],
        "deposits": [
            {
                k: item[k]  # type: ignore[literal-required]
                for k in (
                    "deposit_id",
                    "product",
                    "currency",
                    "principal",
                    "maturity_date",
                    "maturity_amount",
                    "status",
                )
            }
            for item in deposits
        ],
        "total_outstanding": _by_currency(outstanding),
        "total_arrears": _by_currency(arrears),
        "total_deposits": _by_currency(deposited),
    }


def _by_currency(totals: dict[str, Decimal]) -> dict[str, str]:
    return {currency: f"{total:.2f}" for currency, total in sorted(totals.items())}
