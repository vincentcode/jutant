"""A card, set out for staff: whether it can be used, and why recent attempts were declined.

The card system logs each attempt with the scheme's response code. Which declines there were,
how many of each, and what the card's own settings rule out are put together here, in code;
the meaning of a code comes from the bank's card response code reference, searched alongside.
"""

from collections import Counter
from typing import Any

from packs.banking.adapters.base import Authorisation, Card

STATUS = {
    "active": "active",
    "inactive": "not yet activated",
    "blocked": "blocked",
    "hot_listed": "hot-listed (reported lost or stolen)",
    "expired": "expired",
}


def card(record: Card, attempts: list[Authorisation]) -> dict[str, Any]:
    declines = [a for a in attempts if a["result"] == "declined"]
    by_code = Counter(a["response_code"] for a in declines)
    settings = []
    if not record["international_enabled"]:
        settings.append("International use is switched off.")
    if not record["online_enabled"]:
        settings.append("Online payments are switched off.")
    approved = [a["date"] for a in attempts if a["result"] == "approved"]
    return {
        **record,
        "status_in_words": STATUS[record["status"]],
        "usable": record["status"] == "active",
        "settings": settings,
        "recent_attempts": attempts,
        "declines": len(declines),
        "declines_by_code": [
            {
                "response_code": code,
                "times": times,
                "reason": next(
                    a["response_reason"] for a in declines if a["response_code"] == code
                ),
            }
            for code, times in by_code.most_common()
        ],
        "last_approved": approved[0] if approved else None,
    }


def cards(records: list[Card]) -> dict[str, Any]:
    return {
        "cards": [
            {
                k: c[k]  # type: ignore[literal-required]
                for k in (
                    "card_id",
                    "masked_number",
                    "type",
                    "status",
                    "block_reason",
                    "expiry",
                    "account_number",
                )
            }
            for c in records
        ],
        "count": len(records),
        "usable": [c["card_id"] for c in records if c["status"] == "active"],
    }
