"""The transaction service: which systems it asks, and what it makes of their answers."""

import asyncio
from collections.abc import Mapping

import pytest

from packs.banking.adapters import CORE_CHANNELS
from packs.banking.adapters.base import BankUnavailable, NotFound, Transaction
from packs.banking.adapters.core_banking_source import CoreBankingTransactions
from packs.banking.adapters.fake import FakeCoreBanking
from packs.banking.domain.transactions import TransactionService


def row(reference: str, day: str, account: str = "0011223344") -> Transaction:
    return {
        "reference": reference,
        "account_number": account,
        "date": day,
        "amount": "-10.00",
        "direction": "debit",
        "narration": "Transfer",
        "status": "completed",
        "failure_code": None,
        "failure_reason": None,
    }


class System:
    """A stand-in system: records `rows` on `channels`, searchable by `searchable_by`."""

    def __init__(
        self,
        name: str,
        channels: set[str],
        searchable_by: tuple[frozenset[str], ...],
        rows: list[Transaction] = (),
        down: bool = False,
        slow: bool = False,
    ):
        self.name, self.channels, self.searchable_by = name, frozenset(channels), searchable_by
        self.rows, self.down, self.slow = list(rows), down, slow
        self.asked: list[dict[str, str]] = []

    async def search(self, criteria: Mapping[str, str]) -> list[Transaction]:
        self.asked.append(dict(criteria))
        if self.down:
            raise BankUnavailable(self.name)
        if self.slow:
            await asyncio.sleep(1)
        return [r for r in self.rows if all(r.get(k, v) == v for k, v in criteria.items())]


BY_REFERENCE = (frozenset({"reference"}),)
BY_PHONE_AND_DATE = (frozenset({"reference"}), frozenset({"phone", "date"}))


def service(*systems: System) -> TransactionService:
    return TransactionService(systems, FakeCoreBanking(), timeout_s=0.1)


async def test_a_channel_named_is_looked_for_only_where_it_is_recorded() -> None:
    app = System("app", {"mobile_app"}, BY_REFERENCE, [row("MB-1", "2026-10-01")])
    ussd = System("ussd", {"ussd"}, BY_REFERENCE, [row("MB-1", "2026-10-01")])
    found = await service(app, ussd).find("ussd", reference="MB-1")
    assert (found.searched, app.asked) == (["ussd"], [])


async def test_not_sure_asks_every_system_that_can_search_by_what_was_given() -> None:
    app = System("app", {"mobile_app"}, BY_REFERENCE)
    ussd = System(
        "ussd", {"ussd"}, BY_PHONE_AND_DATE, [{**row("US-7", "2026-10-03"), "phone": "0244123456"}]
    )  # type: ignore[typeddict-unknown-key]
    found = await service(app, ussd).find(None, phone="0244123456", date="2026-10-03")
    assert found.searched == ["ussd"]  # the app's system cannot search by phone
    assert [t["reference"] for t in found.transactions] == ["US-7"]


async def test_a_system_down_or_slow_leaves_the_others_answer() -> None:
    core = System("core", {"branch"}, BY_REFERENCE, [row("TX-9", "2026-10-02")])
    down = System("ussd", {"ussd"}, BY_REFERENCE, down=True)
    slow = System("wallet", {"wallet"}, BY_REFERENCE, slow=True)
    found = await service(core, down, slow).find(None, reference="TX-9")
    assert [t["reference"] for t in found.transactions] == ["TX-9"]
    assert found.unavailable == ["ussd", "wallet"]


async def test_one_transaction_held_by_two_systems_is_listed_once_newest_first() -> None:
    app = System(
        "app",
        {"mobile_app"},
        (frozenset({"account_number"}),),
        [row("A", "2026-10-01"), row("B", "2026-10-05")],
    )
    core = System("core", {"branch"}, (frozenset({"account_number"}),), [row("B", "2026-10-05")])
    found = await service(app, core).find(None, account_number="0011223344")
    assert [t["reference"] for t in found.transactions] == ["B", "A"]


async def test_status_says_not_found_or_unavailable() -> None:
    with pytest.raises(NotFound):
        await service(System("core", {"branch"}, BY_REFERENCE)).status("TX-404")
    down = System("ussd", {"ussd"}, BY_REFERENCE, down=True)
    with pytest.raises(BankUnavailable):  # it might be there: not "not found"
        await service(System("core", {"branch"}, BY_REFERENCE), down).status("TX-404")


async def test_core_banking_as_a_source() -> None:
    banking = FakeCoreBanking()
    service = TransactionService([CoreBankingTransactions(banking, CORE_CHANNELS)], banking)
    transaction, account = await service.status("TX-0002")
    assert (transaction["status"], account["branch"]) == ("failed", "ACC-01")
    dated = await service.find("branch", account_number="0011223344", date="2026-09-30")
    assert [t["reference"] for t in dated.transactions] == ["TX-0002"]
    assert (await service.find("ussd", reference="TX-0002")).searched == []  # not core's channel
    assert (await service.find(None, account_number="9999999999")).transactions == []
