"""In-memory card management system, with seed data for the fake bank's customers.

- CRD-3001 (Ama Mensah): active; declined online abroad (international use is off) and at an
  ATM above its daily limit.
- CRD-3002 (Kofi Asante): blocked after too many wrong PINs.
- CRD-3003 (Ama Mensah): her previous card, expired.
"""

from typing import Any

from packs.banking.adapters.base import NotFound

CARDS: dict[str, dict[str, Any]] = {
    "CRD-3001": {
        "card_id": "CRD-3001",
        "customer_number": "C1001",
        "account_number": "0011223344",
        "branch": "ACC-01",
        "masked_number": "5399 **** **** 1234",
        "type": "debit",
        "status": "active",
        "block_reason": None,
        "blocked_on": None,
        "expiry": "2028-05",
        "daily_limit": "3000.00",
        "online_enabled": True,
        "international_enabled": False,
    },
    "CRD-3002": {
        "card_id": "CRD-3002",
        "customer_number": "C1002",
        "account_number": "0099887766",
        "branch": "KSI-02",
        "masked_number": "5399 **** **** 8842",
        "type": "debit",
        "status": "blocked",
        "block_reason": "PIN tries exceeded",
        "blocked_on": "2026-10-05",
        "expiry": "2027-02",
        "daily_limit": "2000.00",
        "online_enabled": True,
        "international_enabled": False,
    },
    "CRD-3003": {
        "card_id": "CRD-3003",
        "customer_number": "C1001",
        "account_number": "0011223344",
        "branch": "ACC-01",
        "masked_number": "5399 **** **** 0457",
        "type": "debit",
        "status": "expired",
        "block_reason": None,
        "blocked_on": None,
        "expiry": "2026-08",
        "daily_limit": "3000.00",
        "online_enabled": True,
        "international_enabled": False,
    },
}


def _auth(day: str, channel: str, merchant: str, amount: str, code: str, reason: str | None):
    return {
        "date": day,
        "channel": channel,
        "merchant": merchant,
        "amount": amount,
        "result": "approved" if code == "00" else "declined",
        "response_code": code,
        "response_reason": reason,
    }


AUTHORISATIONS: dict[str, list[dict[str, Any]]] = {
    "CRD-3001": [
        _auth("2026-10-10", "pos", "Shoprite Accra Mall", "450.00", "00", None),
        _auth(
            "2026-10-09",
            "online",
            "Booking.com (Netherlands)",
            "1200.00",
            "57",
            "Transaction not permitted to cardholder",
        ),
        _auth("2026-10-08", "atm", "GCB ATM Osu", "3500.00", "61", "Exceeds withdrawal limit"),
        _auth("2026-10-02", "pos", "Total Energies Airport", "300.00", "00", None),
    ],
    "CRD-3002": [
        _auth("2026-10-05", "atm", "Bank ATM Adum", "500.00", "75", "PIN tries exceeded"),
        _auth("2026-10-05", "atm", "Bank ATM Adum", "500.00", "55", "Incorrect PIN"),
        _auth("2026-10-05", "atm", "Bank ATM Adum", "500.00", "55", "Incorrect PIN"),
        _auth("2026-09-28", "pos", "Melcom Kumasi", "220.00", "00", None),
    ],
    "CRD-3003": [],
}


class FakeCards:
    async def list_cards(self, customer_number: str) -> list[dict[str, Any]]:
        return [dict(c) for c in CARDS.values() if c["customer_number"] == customer_number]

    async def get_card(self, card_id: str) -> dict[str, Any]:
        if card_id not in CARDS:
            raise NotFound(card_id)
        return dict(CARDS[card_id])

    async def recent_authorisations(self, card_id: str, limit: int = 10) -> list[dict[str, Any]]:
        if card_id not in AUTHORISATIONS:
            raise NotFound(card_id)
        rows = sorted(AUTHORISATIONS[card_id], key=lambda a: a["date"], reverse=True)
        return [dict(a) for a in rows[:limit]]
