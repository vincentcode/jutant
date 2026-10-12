"""Core banking as a transaction source: searched by reference, or by account (and a date).

It works on any core banking client (the fake, or the real one over HTTP), through the methods
every client keeps (`CoreBankingClient`), so it holds no knowledge of the bank's interface.
"""

from collections.abc import Mapping

from packs.banking.adapters.base import CoreBankingClient, NotFound, Transaction

MOST = 20  # transactions on one account for one search


class CoreBankingTransactions:
    name = "core banking"
    searchable_by = (frozenset({"reference"}), frozenset({"account_number"}))

    def __init__(self, banking: CoreBankingClient, channels: frozenset[str]):
        self.banking = banking
        self.channels = channels

    async def search(self, criteria: Mapping[str, str]) -> list[Transaction]:
        try:
            if reference := criteria.get("reference"):
                return [await self.banking.get_transaction(reference)]
            if account := criteria.get("account_number"):
                day = criteria.get("date")
                dated = {"from_date": day, "to_date": day} if day else {}
                return await self.banking.list_transactions(account, limit=MOST, **dated)
        except NotFound:
            return []
        return []
