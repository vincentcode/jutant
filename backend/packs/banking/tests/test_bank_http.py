"""The HTTP layer the real bank clients share: auth, retries, errors and response mapping."""

import httpx
import pytest

from packs.banking.adapters.base import BankUnavailable, NotFound
from packs.banking.adapters.core_banking import HttpCoreBankingClient
from packs.banking.adapters.http import BankHttp, Connection

ACCOUNT = {
    "account_number": "0011223344",
    "customer_number": "C1001",
    "branch": "acc-01",
    "type": "Current",
    "currency": "ghs",
    "balance": 4520.7,
    "status": "ACTIVE",
}


def client(handler, connection: Connection | None = None, retries: int = 1) -> BankHttp:
    return BankHttp(
        connection or Connection("http://bank"),
        retries=retries,
        transport=httpx.MockTransport(handler),
    )


def answering(*responses: httpx.Response | Exception, seen: list[httpx.Request] | None = None):
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    return handler


@pytest.mark.parametrize(
    ("connection", "header", "value"),
    [
        (Connection("http://bank", auth="bearer", token="abc"), "authorization", "Bearer abc"),
        (Connection("http://bank", auth="api_key", token="abc"), "x-api-key", "abc"),
        (
            Connection("http://bank", auth="basic", username="u", password="p"),
            "authorization",
            "Basic dTpw",
        ),
    ],
    ids=["bearer", "api_key", "basic"],
)
async def test_every_request_is_authenticated(connection, header, value) -> None:
    seen: list[httpx.Request] = []
    http = client(answering(httpx.Response(200, json={}), seen=seen), connection)
    await http.get("/x")
    assert seen[0].headers[header] == value


async def test_empty_parameters_are_left_out() -> None:
    seen: list[httpx.Request] = []
    http = client(answering(httpx.Response(200, json=[]), seen=seen))
    await http.get("/x", {"limit": 5, "direction": None})
    assert dict(seen[0].url.params) == {"limit": "5"}


async def test_404_is_not_found() -> None:
    with pytest.raises(NotFound):
        await client(answering(httpx.Response(404))).get("/x")


async def test_a_server_error_is_retried_once() -> None:
    http = client(answering(httpx.Response(503), httpx.Response(200, json={"ok": 1})))
    assert await http.get("/x") == {"ok": 1}


async def test_a_dropped_connection_is_retried_once() -> None:
    http = client(answering(httpx.ConnectError("refused"), httpx.Response(200, json={"ok": 1})))
    assert await http.get("/x") == {"ok": 1}


@pytest.mark.parametrize(
    "responses",
    [
        (httpx.Response(500), httpx.Response(502)),
        (httpx.ConnectError("refused"), httpx.ReadTimeout("slow")),
        (httpx.Response(401),),
        (httpx.Response(400),),
        (httpx.Response(200, text="<html>maintenance</html>"),),
    ],
    ids=["5xx twice", "no connection twice", "unauthorised", "bad request", "not json"],
)
async def test_failures_are_bank_unavailable(responses) -> None:
    with pytest.raises(BankUnavailable):
        await client(answering(*responses)).get("/x")


async def test_a_client_error_is_not_retried() -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(BankUnavailable):
        await client(answering(httpx.Response(401), seen=seen)).get("/x")
    assert len(seen) == 1


async def test_responses_are_normalised_to_the_contract() -> None:
    banking = HttpCoreBankingClient(client(answering(httpx.Response(200, json=ACCOUNT))))
    account = await banking.get_account("0011223344")
    assert account["branch"] == "ACC-01" and account["currency"] == "GHS"
    assert account["balance"] == "4520.70" and account["status"] == "active"


async def test_debits_are_negative_and_timestamps_become_dates() -> None:
    row = {
        "reference": "tx-1",
        "account_number": "0011223344",
        "date": "2026-09-30T14:02:11Z",
        "amount": "1,200.00",
        "direction": "DEBIT",
        "narration": "Transfer",
        "status": "completed",
        "failure_code": "",
    }
    banking = HttpCoreBankingClient(client(answering(httpx.Response(200, json=row))))
    transaction = await banking.get_transaction("TX-1")
    assert transaction["amount"] == "-1200.00" and transaction["date"] == "2026-09-30"
    assert transaction["reference"] == "TX-1" and transaction["failure_code"] is None


async def test_transactions_are_filtered_sorted_and_limited_even_if_the_bank_does_not() -> None:
    def row(reference: str, day: str, direction: str) -> dict:
        return {
            "reference": reference,
            "account_number": "0011223344",
            "date": f"2026-09-{day}",
            "amount": "10.00",
            "direction": direction,
            "status": "completed",
        }

    rows = [
        row("A", "01", "debit"),
        row("B", "20", "credit"),
        row("C", "10", "debit"),
        row("D", "15", "debit"),
        row("E", "28", "debit"),
    ]
    banking = HttpCoreBankingClient(client(answering(httpx.Response(200, json=rows))))
    found = await banking.list_transactions(
        "0011223344", direction="debit", from_date="2026-09-05", to_date="2026-09-25", limit=1
    )
    assert [t["reference"] for t in found] == ["D"]


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in ACCOUNT.items() if k != "branch"},
        {**ACCOUNT, "status": "frozen-ish"},
        {**ACCOUNT, "balance": "n/a"},
        ["not", "an", "object"],
    ],
    ids=["missing field", "unknown status", "bad amount", "wrong kind"],
)
async def test_an_unexpected_response_is_unavailable_not_missing(body) -> None:
    """A changed interface must show as an outage in the logs, never as "no such account"."""
    banking = HttpCoreBankingClient(client(answering(httpx.Response(200, json=body))))
    with pytest.raises(BankUnavailable):
        await banking.get_account("0011223344")


async def test_values_are_escaped_into_one_path_segment() -> None:
    seen: list[httpx.Request] = []
    banking = HttpCoreBankingClient(client(answering(httpx.Response(404), seen=seen)))
    with pytest.raises(NotFound):
        await banking.get_account("../admin?x=1")
    assert seen[0].url.raw_path == b"/accounts/..%2Fadmin%3Fx%3D1"


def test_connection_from_environment() -> None:
    connection = Connection.from_env(
        "BANK",
        {
            "BANK_URL": "https://core.bank",
            "BANK_AUTH": "Bearer",
            "BANK_TOKEN": "abc",
            "BANK_TIMEOUT_S": "4",
        },
    )
    assert connection == Connection("https://core.bank", auth="bearer", token="abc", timeout_s=4)


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"BANK_URL": "https://core.bank", "BANK_AUTH": "magic"},
        {"BANK_URL": "https://core.bank", "BANK_AUTH": "bearer"},
        {"BANK_URL": "https://core.bank", "BANK_AUTH": "basic", "BANK_USERNAME": "u"},
    ],
    ids=["no url", "unknown auth", "bearer without token", "basic without password"],
)
def test_incomplete_settings_are_refused_at_start(env) -> None:
    with pytest.raises(ValueError):
        Connection.from_env("BANK", env)
