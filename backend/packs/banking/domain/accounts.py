"""An account's status, set out for staff: whether money can leave it, and if not, why.

"Why can't the customer withdraw?" is answered from several fields: the account's status, its
debit block, each hold and what it holds back. A small model asked to work that out from the
raw record misreads it (it adds the holds up wrongly, or misses the block), so the answer's
facts are put together here, in code, and the model words them.
"""

from decimal import Decimal
from typing import Any

from packs.banking.adapters.base import AccountStatus, Charge, Cheque, Hold, StandingOrder

HOLD_NAMES = {
    "lien": "Lien",
    "block": "Block",
    "garnishment": "Court order (garnishment)",
    "uncleared_funds": "Uncleared funds",
    "other": "Hold",
}
CHEQUE_STATUS = {
    "unused": "not yet used",
    "in_clearing": "in clearing",
    "paid": "paid",
    "returned": "returned unpaid",
    "stopped": "stopped by the account holder",
}


def overview(status: AccountStatus) -> dict[str, Any]:
    """The status, with what is held, whether money can leave, and the reasons it cannot."""
    currency = status["currency"]
    held = sum((Decimal(h["amount"]) for h in status["holds"] if h["amount"]), Decimal(0))
    restrictions = [_restriction(h, currency) for h in status["holds"]]
    if status["status"] != "active":
        since = f" since {status['dormant_since']}" if status["dormant_since"] else ""
        restrictions.insert(0, f"The account is {status['status']}{since}.")
    if status["debits_blocked"]:
        restrictions.insert(0, "No money may leave the account (debits are blocked).")
    if status["credits_blocked"]:
        restrictions.append("No money may come into the account (credits are blocked).")
    whole = any(h["amount"] is None for h in status["holds"])
    can_withdraw = (
        status["status"] == "active"
        and not status["debits_blocked"]
        and not whole
        and Decimal(status["available_balance"]) > 0
    )
    return {
        "account_number": status["account_number"],
        "status": status["status"],
        "currency": currency,
        "ledger_balance": status["ledger_balance"],
        "available_balance": status["available_balance"],
        "held_amount": f"{held:.2f}",
        "withdrawals_allowed": can_withdraw,
        "why_money_is_held_or_blocked": restrictions,
        "holds": status["holds"],
        "daily_withdrawal_limit": status["daily_withdrawal_limit"],
        "overdraft_limit": status["overdraft_limit"],
    }


def _restriction(hold: Hold, currency: str) -> str:
    name = HOLD_NAMES[hold["type"]]
    what = f"holds {hold['amount']} {currency}" if hold["amount"] else "covers the whole account"
    until = f", until {hold['expires_on']}" if hold["expires_on"] else ""
    by = f", placed by {hold['placed_by']}" if hold["placed_by"] else ""
    return f"{name} {hold['id']} {what}: {hold['reason']} (since {hold['placed_on']}{by}{until})."


def charges(rows: list[Charge]) -> dict[str, Any]:
    """The charges, and their total, added up here."""
    total = sum((Decimal(c["amount"]) for c in rows), Decimal(0))
    return {"charges": rows, "count": len(rows), "total": f"{total:.2f}"}


def standing_orders(rows: list[StandingOrder]) -> dict[str, Any]:
    failed = [o["id"] for o in rows if o["last_result"] == "failed"]
    return {"standing_orders": rows, "count": len(rows), "last_run_failed": failed}


def cheque(record: Cheque) -> dict[str, Any]:
    return {**record, "status_in_words": CHEQUE_STATUS[record["status"]]}
