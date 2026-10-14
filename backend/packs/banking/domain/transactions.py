"""Transactions, whichever system recorded them.

Customers transact through several channels (branch, mobile app, USSD, wallet pull and push),
each recorded by a system of its own, which can be searched by different details. The service
knows the bank's transaction sources (`TransactionSource`) and:

- looks in the systems that record the channel staff named; when they are not sure (no
  channel), in every system that can search by what they gave. It never guesses a channel:
  that is staff's to say (`core.features.needs` asks them);
- asks those systems at once, each with a time limit, and keeps what came back when one does
  not answer, saying which (`Found.unavailable`): an answer from the others, not a failure;
- lists a transaction once, when two systems hold it under the same reference.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from packs.banking.adapters.base import (
    Account,
    BankUnavailable,
    CoreBankingClient,
    NotFound,
    Transaction,
    TransactionSource,
)

TIMEOUT_S = 10.0
CRITERIA = ("reference", "account_number", "phone", "date")


@dataclass(frozen=True)
class Found:
    """What a search found: newest first, each once; the systems searched, and those that did
    not answer."""

    transactions: list[Transaction] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)


class TransactionService:
    def __init__(
        self,
        sources: Sequence[TransactionSource],
        accounts: CoreBankingClient,
        timeout_s: float = TIMEOUT_S,
    ):
        self.sources = tuple(sources)
        self.accounts = accounts  # the system of record for accounts: their branch, currency
        self.timeout_s = timeout_s

    def sources_for(self, channel: str | None, criteria: dict[str, str]) -> list[TransactionSource]:
        """The systems to ask: those recording `channel` (all, if None) that can search by
        some of the `criteria` given."""
        return [
            s
            for s in self.sources
            if (channel is None or channel in s.channels)
            and any(needed <= criteria.keys() for needed in s.searchable_by)
        ]

    async def find(self, channel: str | None = None, **criteria: str | None) -> Found:
        """Transactions matching every criterion given (reference, account_number, phone,
        date), on `channel` or on any channel."""
        given = {k: v for k, v in criteria.items() if k in CRITERIA and v}
        sources = self.sources_for(channel, given)
        answers = await asyncio.gather(*(self._ask(s, given) for s in sources))
        rows: dict[str, Transaction] = {}
        unavailable = []
        for source, answer in zip(sources, answers, strict=True):
            if answer is None:
                unavailable.append(source.name)
                continue
            for row in answer:
                if _fits(row, given):
                    rows.setdefault(row["reference"], row)
        ordered = sorted(rows.values(), key=lambda r: r["date"], reverse=True)
        return Found(ordered, [s.name for s in sources], unavailable)

    async def status(
        self, reference: str, channel: str | None = None
    ) -> tuple[Transaction, Account]:
        """One transaction by its reference, with the account it belongs to. Raises NotFound,
        or BankUnavailable when it was not found and a system that might hold it did not
        answer."""
        found = await self.find(channel, reference=reference)
        if not found.transactions:
            if found.unavailable:
                raise BankUnavailable(f"no answer from {', '.join(found.unavailable)}")
            raise NotFound(reference)
        transaction = found.transactions[0]
        return transaction, await self.accounts.get_account(transaction["account_number"])

    async def statement(
        self, account_number: str, **filters: Any
    ) -> tuple[Account, list[Transaction]]:
        """One account and its transactions, newest first (filters as `list_transactions`)."""
        account = await self.accounts.get_account(account_number)
        return account, await self.accounts.list_transactions(account_number, **filters)

    async def _ask(
        self, source: TransactionSource, criteria: dict[str, str]
    ) -> list[Transaction] | None:
        try:
            return await asyncio.wait_for(source.search(criteria), self.timeout_s)
        except (BankUnavailable, TimeoutError):
            return None


def _fits(row: Transaction, criteria: dict[str, str]) -> bool:
    """The record matches each criterion it carries a field for (a system may search by fewer
    than were given)."""
    return all(row.get(key) in (None, value) for key, value in criteria.items())
