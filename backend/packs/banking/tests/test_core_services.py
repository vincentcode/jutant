"""The core banking services' tools (accounts, lending, cards) and the customer summary, through
the real guard and the pack's own rules, on the fake bank; and the facts set out in code."""

from datetime import date

from core.types import Citation
from packs.banking.adapters.fake_lending import DEPOSITS
from packs.banking.domain import lending
from packs.banking.tests.test_tools import call, staff

# --- accounts -----------------------------------------------------------------------------------


async def test_why_money_cannot_leave_is_set_out_in_code() -> None:
    result = await call("accounts.get_status", account_number="0011223344")
    assert result.ok
    data = result.data
    assert (data["can_withdraw"], data["available_balance"], data["held_amount"]) == (
        True,
        "2220.75",
        "2300.00",
    )
    assert data["restrictions"][0].startswith("Lien H-501 holds 1500.00 GHS")
    assert result.citations == (Citation("record", "Account", "0011223344"),)


async def test_a_dormant_account_says_nothing_may_leave() -> None:
    manager = staff("branch_manager", "ACC-01")  # any branch
    result = await call("accounts.get_status", manager, account_number="0099887766")
    assert result.data["can_withdraw"] is False
    assert result.data["restrictions"][:2] == [
        "No money may leave the account (debits are blocked).",
        "The account is dormant since 2025-04-10.",
    ]


async def test_another_branchs_account_is_refused_on_every_account_tool() -> None:
    for tool, arguments in (
        ("accounts.get_status", {}),
        ("accounts.get_mandate", {}),
        ("accounts.list_charges", {}),
        ("accounts.list_standing_orders", {}),
        ("accounts.get_cheque", {"cheque_number": "000101"}),
    ):
        result = await call(tool, staff(branch="ACC-01"), account_number="0099887766", **arguments)
        assert (result.ok, result.error) == (False, "denied"), tool


async def test_charges_are_totalled_and_failed_standing_orders_named() -> None:
    charges = await call("accounts.list_charges", account_number="0011223344")
    assert (charges.data["count"], charges.data["total"]) == (3, "-62.50")
    orders = await call("accounts.list_standing_orders", account_number="0011223344")
    assert orders.data["last_run_failed"] == ["SO-301"]


async def test_a_cheque_says_why_it_was_returned() -> None:
    result = await call("accounts.get_cheque", account_number="0011223344", cheque_number="000102")
    assert (result.data["status_in_words"], result.data["return_code"]) == (
        "returned unpaid",
        "R01",
    )
    missing = await call("accounts.get_cheque", account_number="0011223344", cheque_number="123456")
    assert (missing.ok, missing.data["found"]) == (True, False)  # on the caller's own branch


# --- lending ------------------------------------------------------------------------------------


async def test_a_loan_in_arrears_with_its_overdue_instalments() -> None:
    officer = staff("credit_officer", "KSI-02")
    result = await call("lending.get_loan", officer, loan_id="ln-1002")
    data = result.data
    assert (data["overdue_instalments"], data["overdue_amount"], data["oldest_overdue"]) == (
        2,
        "4230.00",
        "2026-08-25",
    )
    assert (data["principal_repaid"], data["status_in_words"]) == ("8800.00", "in arrears")


async def test_tellers_may_not_see_loans_and_others_only_their_branchs() -> None:
    teller = await call("lending.get_loan", staff("teller", "ACC-01"), loan_id="LN-1001")
    assert (teller.ok, teller.error) == (False, "denied")
    elsewhere = await call("lending.get_loan", staff("credit_officer", "ACC-01"), loan_id="LN-1002")
    assert (elsewhere.ok, elsewhere.error) == (False, "denied")


async def test_a_customers_facilities_with_totals() -> None:
    result = await call(
        "lending.list_facilities", staff("customer_service", "ACC-01"), customer_number="c1001"
    )
    data = result.data
    assert [loan["loan_id"] for loan in data["loans"]] == ["LN-1001", "LN-1003"]
    assert (data["total_outstanding"], data["total_deposits"]) == (
        {"GHS": "12450.00"},
        {"GHS": "10000.00"},
    )


def test_a_deposit_earns_what_the_system_says_and_counts_down() -> None:
    running = lending.deposit(DEPOSITS["FD-2001"], today=date(2026, 12, 1))  # type: ignore[arg-type]
    assert (running["interest_at_maturity"], running["days_to_maturity"]) == ("900.00", 31)
    matured = lending.deposit(DEPOSITS["FD-2002"], today=date(2026, 10, 12))  # type: ignore[arg-type]
    assert (matured["matured"], matured["days_to_maturity"]) == (True, 0)


# --- cards --------------------------------------------------------------------------------------


async def test_a_card_says_why_it_was_declined() -> None:
    result = await call("cards.get_card", card_id="CRD-3001")
    data = result.data
    assert data["masked_number"] == "5399 **** **** 1234"
    assert [d["response_code"] for d in data["declines_by_code"]] == ["57", "61"]
    assert data["settings"] == ["International use is switched off."]
    assert data["last_approved"] == "2026-10-10"


async def test_a_blocked_card_counts_its_wrong_pins() -> None:
    result = await call("cards.get_card", staff(branch="KSI-02"), card_id="CRD-3002")
    assert (result.data["usable"], result.data["block_reason"]) == (False, "PIN tries exceeded")
    assert result.data["declines_by_code"][0] == {
        "response_code": "55",
        "times": 2,
        "reason": "Incorrect PIN",
    }


async def test_a_customers_cards_and_another_branchs_refused() -> None:
    mine = await call("cards.list_cards", customer_number="C1001")
    assert (mine.data["count"], mine.data["usable"]) == (2, ["CRD-3001"])
    theirs = await call("cards.list_cards", staff(branch="ACC-01"), customer_number="C1002")
    assert (theirs.ok, theirs.error) == (False, "denied")


# --- the customer summary -----------------------------------------------------------------------


async def test_the_summary_adds_kyc_facilities_cards_and_what_needs_attention() -> None:
    result = await call(
        "services.customer_summary", staff("customer_service", "KSI-02"), customer_number="C1002"
    )
    data = result.data
    assert data["kyc"]["status"] == "review_due"
    assert data["attention"] == [
        "Account 0099887766 is dormant.",
        "KYC is review due (review due 2026-09-01).",
        "Missing KYC documents: proof of address.",
        "Loan LN-1002 is 47 days past due (4230.00 GHS in arrears).",
        "Card CRD-3002 is blocked: PIN tries exceeded.",
    ]
    assert data["total_arrears"] == {"GHS": "4230.00"}
