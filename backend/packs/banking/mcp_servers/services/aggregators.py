"""The customer summary, assembled in code from the bank's systems.

Every figure is computed here, with decimal arithmetic, so the model only writes prose around
numbers it is given and never adds anything up itself. What needs staff's attention (a KYC
review overdue, a loan in arrears, a blocked card, a dormant account) is listed in plain words
(`attention`), so the model does not have to spot it in the figures.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from packs.banking.adapters.base import (
    CardsClient,
    CoreBankingClient,
    CustomerRecordsClient,
    LendingClient,
    NotFound,
    ServiceCatalogClient,
)
from packs.banking.domain import lending as lending_facts

RECENT_TRANSACTIONS = 5


async def customer_summary(
    banking: CoreBankingClient,
    catalog: ServiceCatalogClient,
    customer_number: str,
    *,
    customers: CustomerRecordsClient | None = None,
    lending: LendingClient | None = None,
    cards: CardsClient | None = None,
) -> dict[str, Any]:
    """Accounts and balances, the latest transactions across all accounts, open requests, flags;
    with `customers`, `lending` and `cards`, the KYC record, loans, deposits and cards too."""
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
    extra = await _beyond_accounts(customer_number, customers, lending, cards)
    attention = [
        f"Account {a['account_number']} is {a.get('status')}."
        for a in accounts
        if a.get("status") in ("dormant", "blocked", "closed")
    ] + extra.pop("attention")
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
        **extra,
        "attention": attention,
    }


async def _beyond_accounts(
    customer_number: str,
    customers: CustomerRecordsClient | None,
    lending: LendingClient | None,
    cards: CardsClient | None,
) -> dict[str, Any]:
    """KYC, loans and deposits, and cards, from the systems that hold them, with what needs
    attention."""
    found: dict[str, Any] = {}
    attention: list[str] = []
    if customers is not None:
        try:
            kyc = await customers.get_kyc(customer_number)
        except NotFound:
            kyc = None
        if kyc is not None:
            found["kyc"] = {
                k: kyc[k]  # type: ignore[literal-required]
                for k in ("status", "risk_rating", "next_review", "id_expiry", "missing_documents")
            }
            if kyc["status"] != "verified":
                due = f" (review due {kyc['next_review']})" if kyc["next_review"] else ""
                attention.append(f"KYC is {kyc['status'].replace('_', ' ')}{due}.")
            if kyc["missing_documents"]:
                attention.append(f"Missing KYC documents: {', '.join(kyc['missing_documents'])}.")
    if lending is not None:
        facilities = lending_facts.facilities(
            await lending.list_loans(customer_number), await lending.list_deposits(customer_number)
        )
        found.update(facilities)
        for loan in facilities["loans"]:
            if loan["days_past_due"]:
                attention.append(
                    f"Loan {loan['loan_id']} is {loan['days_past_due']} days past due "
                    f"({loan['arrears_amount']} {loan['currency']} in arrears)."
                )
    if cards is not None:
        held = await cards.list_cards(customer_number)
        found["cards"] = [
            {k: c[k] for k in ("card_id", "masked_number", "status", "block_reason")}  # type: ignore[literal-required]
            for c in held
        ]
        for card in held:
            if card["status"] in ("blocked", "hot_listed"):
                why = f": {card['block_reason']}" if card["block_reason"] else ""
                attention.append(f"Card {card['card_id']} is {card['status']}{why}.")
    found["attention"] = attention
    return found


def _amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)
