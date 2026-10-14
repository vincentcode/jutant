"""Interfaces for the bank's systems. The MCP tools depend on these, so a real client and
an in-memory fake can be swapped without changing the tools.

The record types below are what every client returns, whatever the bank's own field names
are: a real client maps the bank's responses into them. `tests/test_adapter_contract.py`
checks every client against them, the fakes included.

Conventions: money is a decimal string ("4520.75", "-250.00"; debits negative), dates are
ISO (YYYY-MM-DD), codes and references are upper case.
"""

from collections.abc import Mapping
from typing import Any, Literal, NotRequired, Protocol, TypedDict


class NotFound(LookupError):
    """The record does not exist. The tools report it as `not_found`."""


class BankUnavailable(Exception):
    """The bank's system could not be reached or answered with an error. The tools report it
    as `upstream_error`; the message is for the logs, never shown to staff."""


class Account(TypedDict):
    account_number: str
    customer_number: str
    branch: str  # the branch rule compares this with the caller's branch
    type: str  # current, savings...
    currency: str
    balance: str
    status: Literal["active", "dormant", "closed", "blocked"]


class Transaction(TypedDict):
    reference: str
    account_number: str
    date: str
    amount: str
    direction: Literal["debit", "credit"]
    narration: str
    status: Literal["completed", "pending", "failed", "reversed"]
    failure_code: str | None
    failure_reason: str | None


class Customer(TypedDict):
    customer_number: str
    name: str
    branch: str
    flags: list[str]  # e.g. kyc_review_due
    accounts: list[str]  # account numbers


class ProductMatch(TypedDict):
    code: str
    name: str


class Product(TypedDict):
    code: str
    name: str
    rate: str
    fees: dict[str, str]
    eligibility: str
    required_documents: list[str]


class Requirements(TypedDict):
    request_type: str
    forms: list[str]
    signatures: list[str]
    approvals: list[str]


class OpenRequest(TypedDict):
    id: str
    type: str
    status: str
    opened: NotRequired[str]


class CoreBankingClient(Protocol):
    async def get_account(self, account_number: str) -> Account: ...

    async def list_transactions(self, account_number: str, **filters: Any) -> list[Transaction]:
        """Newest first. Filters: from_date, to_date (inclusive), direction, limit (default 5).
        An account with no transactions gives []; an unknown account raises NotFound."""
        ...

    async def get_transaction(self, reference: str) -> Transaction: ...
    async def get_customer(self, customer_number: str) -> Customer: ...


class TransactionSource(Protocol):
    """A system that records transactions, as the transaction service asks it
    (`packs.banking.domain.transactions`): which channels it records, and which sets of details
    it can search by. Core banking is one; the mobile app's, USSD's and the wallet gateway's
    systems are others."""

    name: str  # for staff and the logs: "core banking"
    channels: frozenset[str]  # the pack's channel ids it records: "branch", "ussd"...
    # Each set is enough to search by: {"reference"}, {"phone", "date"}...
    searchable_by: tuple[frozenset[str], ...]

    async def search(self, criteria: Mapping[str, str]) -> list[Transaction]:
        """Transactions matching `criteria` (reference, account_number, phone, date), newest
        first; none gives []. Raises BankUnavailable when the system does not answer."""
        ...


class ServiceCatalogClient(Protocol):
    async def search_products(self, query: str) -> list[ProductMatch]:
        """Best match first; no match gives []."""
        ...

    async def get_product(self, code: str) -> Product: ...
    async def get_requirements(self, request_type: str) -> Requirements: ...

    async def open_requests(self, customer_number: str) -> list[OpenRequest]:
        """A customer with no open requests gives []."""
        ...


# --- Account services: what a core banking system holds about an account beyond its balance ----


class Hold(TypedDict):
    """Something stopping money on an account being used: a lien for a loan, a court order, a
    block placed by fraud or compliance, funds not yet cleared."""

    id: str
    type: Literal["lien", "block", "garnishment", "uncleared_funds", "other"]
    amount: str | None  # None: the whole account
    reason: str
    placed_on: str
    expires_on: str | None
    placed_by: str  # the unit: Credit, Legal, Fraud, Compliance...


class AccountStatus(TypedDict):
    account_number: str
    branch: str
    status: Literal["active", "dormant", "closed", "blocked"]
    currency: str
    ledger_balance: str
    available_balance: str
    debits_blocked: bool  # no money may leave
    credits_blocked: bool  # no money may come in
    dormant_since: str | None
    holds: list[Hold]
    daily_withdrawal_limit: str
    overdraft_limit: str


class Signatory(TypedDict):
    customer_number: str
    name: str
    role: Literal["primary", "joint", "authorised"]


class Mandate(TypedDict):
    """Who may operate an account, and how many must sign."""

    account_number: str
    rule: str  # "any one to sign", "both to sign", "A and any one of B"
    signatories: list[Signatory]


class Charge(TypedDict):
    reference: str
    account_number: str
    date: str
    amount: str  # negative: taken from the account
    fee_code: str  # the fee schedule's code, to look its terms up
    description: str


class StandingOrder(TypedDict):
    id: str
    account_number: str
    beneficiary: str
    amount: str
    frequency: Literal["weekly", "monthly", "quarterly", "yearly"]
    next_run: str | None
    last_run: str | None
    last_result: Literal["paid", "failed"] | None
    failure_reason: str | None
    status: Literal["active", "suspended", "ended"]


class Cheque(TypedDict):
    account_number: str
    cheque_number: str
    status: Literal["unused", "in_clearing", "paid", "returned", "stopped"]
    amount: str | None
    payee: str | None
    presented_on: str | None
    return_code: str | None  # the clearing house's reason code
    return_reason: str | None


class AccountServicesClient(Protocol):
    """Each method raises NotFound for an unknown account (or cheque)."""

    async def get_status(self, account_number: str) -> AccountStatus: ...
    async def get_mandate(self, account_number: str) -> Mandate: ...

    async def list_charges(self, account_number: str, **filters: Any) -> list[Charge]:
        """Newest first. Filters: from_date, to_date (inclusive), limit (default 10)."""
        ...

    async def list_standing_orders(self, account_number: str) -> list[StandingOrder]: ...
    async def get_cheque(self, account_number: str, cheque_number: str) -> Cheque: ...


# --- Customers: what is known about a customer beyond their accounts ----------------------------


class Kyc(TypedDict):
    customer_number: str
    status: Literal["verified", "review_due", "expired", "incomplete"]
    risk_rating: Literal["low", "medium", "high"]
    last_review: str | None
    next_review: str | None
    id_type: str | None
    id_expiry: str | None
    missing_documents: list[str]


class CustomerRecordsClient(Protocol):
    async def get_kyc(self, customer_number: str) -> Kyc: ...


# --- Lending and deposits: loans and term deposits, often a system of their own ----------------


class Loan(TypedDict):
    loan_id: str
    customer_number: str
    branch: str
    product: str
    currency: str
    principal: str
    outstanding: str
    rate: str  # yearly, as a percentage: "24.0"
    start_date: str
    maturity_date: str
    repayment_account: str
    next_due_date: str | None
    next_due_amount: str | None
    arrears_amount: str
    days_past_due: int
    status: Literal["pending_disbursement", "current", "in_arrears", "restructured", "closed"]


class Instalment(TypedDict):
    due_date: str
    amount: str
    principal: str
    interest: str
    paid: str
    status: Literal["paid", "partly_paid", "overdue", "due"]


class Deposit(TypedDict):
    deposit_id: str
    customer_number: str
    branch: str
    product: str
    currency: str
    principal: str
    rate: str
    start_date: str
    maturity_date: str
    maturity_amount: str  # as the system calculated it
    rollover: Literal["none", "principal", "principal_and_interest"]
    early_withdrawal_penalty: str  # as the system states it: "2% of principal"
    status: Literal["running", "matured", "closed"]


class LendingClient(Protocol):
    """A customer with none gives []; an unknown loan or deposit raises NotFound."""

    async def list_loans(self, customer_number: str) -> list[Loan]: ...
    async def get_loan(self, loan_id: str) -> Loan: ...

    async def get_schedule(self, loan_id: str) -> list[Instalment]:
        """Oldest first."""
        ...

    async def list_deposits(self, customer_number: str) -> list[Deposit]: ...
    async def get_deposit(self, deposit_id: str) -> Deposit: ...


# --- Cards: a card management system ------------------------------------------------------------


class Card(TypedDict):
    card_id: str
    customer_number: str
    account_number: str
    branch: str
    masked_number: str  # never the full card number: "5399 **** **** 1234"
    type: Literal["debit", "credit", "prepaid"]
    status: Literal["active", "inactive", "blocked", "hot_listed", "expired"]
    block_reason: str | None
    blocked_on: str | None
    expiry: str  # YYYY-MM
    daily_limit: str
    online_enabled: bool
    international_enabled: bool


class Authorisation(TypedDict):
    """An attempt to use a card, approved or declined, as the card system logged it."""

    date: str
    channel: Literal["atm", "pos", "online"]
    merchant: str
    amount: str
    result: Literal["approved", "declined"]
    response_code: str  # the scheme's: "00" approved, "51" insufficient funds...
    response_reason: str | None


class CardsClient(Protocol):
    async def list_cards(self, customer_number: str) -> list[Card]: ...
    async def get_card(self, card_id: str) -> Card: ...

    async def recent_authorisations(self, card_id: str, limit: int = 10) -> list[Authorisation]:
        """Newest first."""
        ...
