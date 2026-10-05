"""The contract every client for the bank's systems keeps, checked on each of them.

Runs on the in-memory fakes and on the real HTTP clients talking to the mock bank (in-process,
no network). A client written for the bank's real interface is added to `CLIENTS` and must pass
the same tests; run them against the bank's test environment before going live.
"""

import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import httpx
import pytest

from packs.banking.adapters import BankSystems
from packs.banking.adapters.base import (
    Account,
    Customer,
    NotFound,
    OpenRequest,
    Product,
    ProductMatch,
    Requirements,
    Transaction,
)
from packs.banking.adapters.core_banking import HttpCoreBankingClient
from packs.banking.adapters.fake import FakeCoreBanking, FakeServiceCatalog
from packs.banking.adapters.http import BankHttp, Connection
from packs.banking.adapters.service_catalog import HttpServiceCatalogClient
from packs.banking.mock_bank import create_app

MONEY = re.compile(r"^-?\d+\.\d{2}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@asynccontextmanager
async def fake() -> AsyncIterator[BankSystems]:
    yield BankSystems(FakeCoreBanking(), FakeServiceCatalog())


@asynccontextmanager
async def http_on_mock_bank() -> AsyncIterator[BankSystems]:
    transport = httpx.ASGITransport(app=create_app(token="t0ken"))
    connection = Connection("http://mock-bank", auth="bearer", token="t0ken")
    banking, catalog = (
        BankHttp(connection, transport=transport),
        BankHttp(connection, transport=transport),
    )
    try:
        yield BankSystems(HttpCoreBankingClient(banking), HttpServiceCatalogClient(catalog))
    finally:
        await banking.close()
        await catalog.close()


CLIENTS: dict[str, Callable[[], Any]] = {"fake": fake, "http": http_on_mock_bank}


@pytest.fixture(params=list(CLIENTS))
async def bank(request: pytest.FixtureRequest) -> AsyncIterator[BankSystems]:
    async with CLIENTS[request.param]() as systems:
        yield systems


def assert_shape(record: Any, kind: type) -> None:
    """The record has exactly the type's fields (optional ones may be missing), each of the
    declared kind."""
    hints = get_type_hints(kind)
    assert isinstance(record, dict), record
    assert kind.__required_keys__ <= record.keys() <= hints.keys(), (kind.__name__, record)
    for key, value in record.items():
        assert _matches(value, hints[key]), f"{kind.__name__}.{key} = {value!r}"


def _matches(value: Any, hint: Any) -> bool:
    origin, args = get_origin(hint), get_args(hint)
    if origin is Literal:
        return value in args
    if origin in (Union, type(str | None)):
        return any(_matches(value, a) for a in args)
    if origin is list:
        return isinstance(value, list) and all(_matches(v, args[0]) for v in value)
    if origin is dict:
        return isinstance(value, dict) and all(
            _matches(k, args[0]) and _matches(v, args[1]) for k, v in value.items()
        )
    if hint is type(None):
        return value is None
    return isinstance(value, hint)


# --- core banking -----------------------------------------------------------------------


async def test_an_account(bank: BankSystems) -> None:
    account = await bank.banking.get_account("0011223344")
    assert_shape(account, Account)
    assert account["account_number"] == "0011223344" and account["branch"] == "ACC-01"
    assert MONEY.match(account["balance"])


async def test_transactions_are_newest_first_and_limited(bank: BankSystems) -> None:
    rows = await bank.banking.list_transactions("0011223344", limit=2)
    for row in rows:
        assert_shape(row, Transaction)
        assert DATE.match(row["date"]) and MONEY.match(row["amount"])
    assert [r["reference"] for r in rows] == ["TX-0003", "TX-0002"]


async def test_transactions_default_to_five(bank: BankSystems) -> None:
    assert len(await bank.banking.list_transactions("0011223344")) <= 5


async def test_transaction_filters(bank: BankSystems) -> None:
    debits = await bank.banking.list_transactions("0011223344", direction="debit", limit=10)
    assert debits and all(r["direction"] == "debit" for r in debits)
    assert all(r["amount"].startswith("-") for r in debits)  # debits are negative
    dated = await bank.banking.list_transactions(
        "0011223344", from_date="2026-09-29", to_date="2026-09-30", limit=10
    )
    assert [r["reference"] for r in dated] == ["TX-0002"]


async def test_an_account_with_no_matching_transactions_gives_none(bank: BankSystems) -> None:
    assert await bank.banking.list_transactions("0011223344", from_date="2030-01-01") == []


async def test_a_failed_transaction_says_why(bank: BankSystems) -> None:
    transaction = await bank.banking.get_transaction("TX-0002")
    assert_shape(transaction, Transaction)
    assert transaction["status"] == "failed"
    assert transaction["failure_code"] == "E51" and transaction["failure_reason"]


async def test_a_customer_lists_their_accounts(bank: BankSystems) -> None:
    customer = await bank.banking.get_customer("C1001")
    assert_shape(customer, Customer)
    assert sorted(customer["accounts"]) == ["0011223344", "0011223355"]


@pytest.mark.parametrize(
    "lookup",
    [
        lambda b: b.banking.get_account("0000000000"),
        lambda b: b.banking.list_transactions("0000000000"),
        lambda b: b.banking.get_transaction("TX-9999"),
        lambda b: b.banking.get_customer("C9999"),
        lambda b: b.catalog.get_product("NOPE"),
        lambda b: b.catalog.get_requirements("no_such_request"),
    ],
    ids=["account", "transactions", "transaction", "customer", "product", "requirements"],
)
async def test_a_missing_record_raises_not_found(bank: BankSystems, lookup) -> None:
    with pytest.raises(NotFound):
        await lookup(bank)


async def test_a_value_cannot_reach_another_path(bank: BankSystems) -> None:
    with pytest.raises(NotFound):
        await bank.banking.get_account("../customers/C1001")


# --- service catalogue --------------------------------------------------------------------


async def test_product_search_puts_the_best_match_first(bank: BankSystems) -> None:
    matches = await bank.catalog.search_products("Business Current account")
    for match in matches:
        assert_shape(match, ProductMatch)
    assert matches[0]["code"] == "CUR-BIZ"
    assert await bank.catalog.search_products("zzzz") == []


async def test_a_product(bank: BankSystems) -> None:
    product = await bank.catalog.get_product("SAV-STD")
    assert_shape(product, Product)
    assert all(MONEY.match(fee) for fee in product["fees"].values())


async def test_requirements(bank: BankSystems) -> None:
    requirements = await bank.catalog.get_requirements("joint_account_opening")
    assert_shape(requirements, Requirements)
    assert requirements["forms"]


async def test_open_requests(bank: BankSystems) -> None:
    requests = await bank.catalog.open_requests("C1001")
    assert requests
    for request in requests:
        assert_shape(request, OpenRequest)
    assert await bank.catalog.open_requests("C1002") == []
