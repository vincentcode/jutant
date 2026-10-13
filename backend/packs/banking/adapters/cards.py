"""Real card management client.

PROVISIONAL: the bank has not yet said what its card system exposes, so this client speaks a
plain REST interface of our own (served for development by `packs/banking/mock_bank.py`):

    GET /customers/{customer_number}/cards
    GET /cards/{card_id}
    GET /cards/{card_id}/authorisations?limit=

A card number is never asked for or kept: the bank's response is masked here too, keeping only
its first four and last four digits, in case the system sends more.

When the bank's interface is known, change the paths in the methods and the `to_*` functions
that map its responses to the records in `base.py`. Nothing outside this file needs to change;
`tests/test_adapter_contract.py` shows whether the result still keeps the contract.
"""

import re
from typing import Any

from packs.banking.adapters.base import Authorisation, Card
from packs.banking.adapters.http import (
    BankHttp,
    flag,
    iso_date,
    mapped,
    money,
    one_of,
    optional,
    optional_date,
    segment,
)

DEFAULT_AUTHORISATIONS = 10


class HttpCardsClient:
    def __init__(self, http: BankHttp):
        self.http = http

    async def list_cards(self, customer_number: str) -> list[Card]:
        raw = await self.http.get(f"/customers/{segment(customer_number)}/cards")
        return mapped(lambda items: [to_card(r) for r in items], raw, "card list")

    async def get_card(self, card_id: str) -> Card:
        raw = await self.http.get(f"/cards/{segment(card_id)}")
        return mapped(to_card, raw, "card")

    async def recent_authorisations(
        self, card_id: str, limit: int = DEFAULT_AUTHORISATIONS
    ) -> list[Authorisation]:
        raw = await self.http.get(f"/cards/{segment(card_id)}/authorisations", {"limit": limit})
        rows = mapped(lambda items: [to_authorisation(r) for r in items], raw, "authorisations")
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows[:limit]


def masked(number: Any) -> str:
    """A card number with only its first four and last four digits: "5399 **** **** 1234"."""
    digits = re.sub(r"\D", "", str(number))
    if len(digits) < 8:
        return "**** **** **** ****"
    return f"{digits[:4]} **** **** {digits[-4:]}"


def to_card(raw: dict[str, Any]) -> Card:
    return {
        "card_id": str(raw["card_id"]).upper(),
        "customer_number": str(raw["customer_number"]),
        "account_number": str(raw["account_number"]),
        "branch": str(raw["branch"]).upper(),
        "masked_number": masked(raw.get("masked_number") or raw.get("card_number") or ""),
        "type": one_of(raw["type"], ("debit", "credit", "prepaid")),
        "status": one_of(raw["status"], ("active", "inactive", "blocked", "hot_listed", "expired")),
        "block_reason": optional(raw.get("block_reason")),
        "blocked_on": optional_date(raw.get("blocked_on")),
        "expiry": str(raw["expiry"])[:7],
        "daily_limit": money(raw["daily_limit"]),
        "online_enabled": flag(raw.get("online_enabled")),
        "international_enabled": flag(raw.get("international_enabled")),
    }


def to_authorisation(raw: dict[str, Any]) -> Authorisation:
    code = str(raw["response_code"]).zfill(2)
    return {
        "date": iso_date(raw["date"]),
        "channel": one_of(raw["channel"], ("atm", "pos", "online")),
        "merchant": str(raw.get("merchant") or ""),
        "amount": money(raw["amount"]),
        "result": "approved" if code == "00" else "declined",
        "response_code": code,
        "response_reason": optional(raw.get("response_reason")),
    }
