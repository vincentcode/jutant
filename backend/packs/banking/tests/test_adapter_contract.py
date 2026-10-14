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

from packs.banking.adapters import CORE_CHANNELS, BankSystems, build
from packs.banking.adapters.account_services import (
    HttpAccountServicesClient,
    HttpCustomerRecordsClient,
)
from packs.banking.adapters.base import (
    Account,
    AccountStatus,
    Authorisation,
    Card,
    Charge,
    Cheque,
    Customer,
    Deposit,
    Instalment,
    Kyc,
    Loan,
    Mandate,
    NotFound,
    OpenRequest,
    Product,
    ProductMatch,
    Requirements,
    StandingOrder,
    Transaction,
)
from packs.banking.adapters.cards import HttpCardsClient
from packs.banking.adapters.core_banking import HttpCoreBankingClient
from packs.banking.adapters.core_banking_source import CoreBankingTransactions
from packs.banking.adapters.http import BankHttp, Connection
from packs.banking.adapters.lending import HttpLendingClient
from packs.banking.adapters.service_catalog import HttpServiceCatalogClient
from packs.banking.mock_bank import create_app

MONEY = re.compile(r"^-?\d+\.\d{2}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@asynccontextmanager
async def fake() -> AsyncIterator[BankSystems]:
    yield build("fake")


@asynccontextmanager
async def http_on_mock_bank() -> AsyncIterator[BankSystems]:
    transport = httpx.ASGITransport(app=create_app(token="t0ken"))
    connection = Connection("http://mock-bank", auth="bearer", token="t0ken")
    banking, catalog, lending, cards = (BankHttp(connection, transport=transport) for _ in range(4))
    try:
        yield BankSystems(
            HttpCoreBankingClient(banking),
            HttpServiceCatalogClient(catalog),
            HttpAccountServicesClient(banking),
            HttpCustomerRecordsClient(banking),
            HttpLendingClient(lending),
            HttpCardsClient(cards),
        )
    finally:
        for http in (banking, catalog, lending, cards):
            await http.close()


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
    if hasattr(hint, "__required_keys__"):  # a record inside a record: a hold, a signatory
        assert_shape(value, hint)
        return True
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


async def test_an_empty_product_search_lists_every_product(bank: BankSystems) -> None:
    everything = await bank.catalog.search_products("")
    assert len(everything) > 1 and {"CUR-BIZ", "SAV-STD"} <= {p["code"] for p in everything}


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


async def test_core_banking_is_a_transaction_source(bank: BankSystems) -> None:
    source = CoreBankingTransactions(bank.banking, CORE_CHANNELS)
    [one] = await source.search({"reference": "TX-0002"})
    assert_shape(one, Transaction)
    dated = await source.search({"account_number": "0011223344", "date": "2026-09-30"})
    assert [r["reference"] for r in dated] == ["TX-0002"]
    assert await source.search({"reference": "TX-9999"}) == []
    assert await source.search({"account_number": "9999999999"}) == []


# --- account services -------------------------------------------------------------------------


async def test_an_account_status_with_its_holds(bank: BankSystems) -> None:
    status = await bank.accounts.get_status("0011223344")
    assert_shape(status, AccountStatus)
    assert [h["type"] for h in status["holds"]] == ["lien", "uncleared_funds"]
    assert MONEY.match(status["available_balance"])
    dormant = await bank.accounts.get_status("0099887766")
    assert dormant["debits_blocked"] is True and dormant["holds"][0]["amount"] is None


async def test_a_mandate_names_its_signatories(bank: BankSystems) -> None:
    mandate = await bank.accounts.get_mandate("0011223355")
    assert_shape(mandate, Mandate)
    assert [s["name"] for s in mandate["signatories"]] == ["Ama Mensah", "Yaw Mensah"]


async def test_charges_are_negative_newest_first_and_filtered(bank: BankSystems) -> None:
    charges = await bank.accounts.list_charges("0011223344")
    for charge in charges:
        assert_shape(charge, Charge)
        assert charge["amount"].startswith("-")
    assert [c["fee_code"] for c in charges][0] == "F12"
    september = await bank.accounts.list_charges("0011223344", to_date="2026-09-30")
    assert {c["fee_code"] for c in september} == {"F01", "F07"}


async def test_standing_orders_say_when_the_last_run_failed(bank: BankSystems) -> None:
    orders = await bank.accounts.list_standing_orders("0011223344")
    for order in orders:
        assert_shape(order, StandingOrder)
    failed = next(o for o in orders if o["id"] == "SO-301")
    assert failed["last_result"] == "failed" and failed["failure_reason"]


async def test_a_returned_cheque_gives_its_code(bank: BankSystems) -> None:
    cheque = await bank.accounts.get_cheque("0011223344", "000102")
    assert_shape(cheque, Cheque)
    assert (cheque["status"], cheque["return_code"]) == ("returned", "R01")
    with pytest.raises(NotFound):
        await bank.accounts.get_cheque("0011223344", "999999")


async def test_a_customers_kyc_record(bank: BankSystems) -> None:
    kyc = await bank.customers.get_kyc("C1002")
    assert_shape(kyc, Kyc)
    assert kyc["status"] == "review_due" and kyc["missing_documents"] == ["proof of address"]


# --- lending ------------------------------------------------------------------------------------


async def test_a_customers_loans_and_one_loans_schedule(bank: BankSystems) -> None:
    loans = await bank.lending.list_loans("C1001")
    for loan in loans:
        assert_shape(loan, Loan)
    assert sorted(loan["loan_id"] for loan in loans) == ["LN-1001", "LN-1003"]
    behind = await bank.lending.get_loan("LN-1002")
    assert (behind["status"], behind["days_past_due"]) == ("in_arrears", 47)
    schedule = await bank.lending.get_schedule("LN-1002")
    for instalment in schedule:
        assert_shape(instalment, Instalment)
    assert [i["due_date"] for i in schedule] == sorted(i["due_date"] for i in schedule)


async def test_deposits(bank: BankSystems) -> None:
    [deposit] = await bank.lending.list_deposits("C1001")
    assert_shape(deposit, Deposit)
    assert (await bank.lending.get_deposit("FD-2002"))["status"] == "matured"
    assert await bank.lending.list_deposits("C9999") == []
    with pytest.raises(NotFound):
        await bank.lending.get_loan("LN-9999")


# --- cards --------------------------------------------------------------------------------------


async def test_cards_are_masked_and_say_why_blocked(bank: BankSystems) -> None:
    cards = await bank.cards.list_cards("C1001")
    for card in cards:
        assert_shape(card, Card)
        assert re.fullmatch(r"\d{4} \*{4} \*{4} \d{4}", card["masked_number"])
    blocked = await bank.cards.get_card("CRD-3002")
    assert (blocked["status"], blocked["block_reason"]) == ("blocked", "PIN tries exceeded")


async def test_recent_attempts_newest_first_with_codes(bank: BankSystems) -> None:
    attempts = await bank.cards.recent_authorisations("CRD-3001", 3)
    for attempt in attempts:
        assert_shape(attempt, Authorisation)
    assert len(attempts) == 3 and attempts[0]["date"] >= attempts[-1]["date"]
    assert {a["response_code"] for a in attempts if a["result"] == "declined"} == {"57", "61"}
