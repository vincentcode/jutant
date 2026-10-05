"""Interfaces for the bank's systems. The MCP tools depend on these, so a real client and
an in-memory fake can be swapped without changing the tools.

The record types below are what every client returns, whatever the bank's own field names
are: a real client maps the bank's responses into them. `tests/test_adapter_contract.py`
checks every client against them, the fakes included.

Conventions: money is a decimal string ("4520.75", "-250.00"; debits negative), dates are
ISO (YYYY-MM-DD), codes and references are upper case.
"""

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


class ServiceCatalogClient(Protocol):
    async def search_products(self, query: str) -> list[ProductMatch]:
        """Best match first; no match gives []."""
        ...

    async def get_product(self, code: str) -> Product: ...
    async def get_requirements(self, request_type: str) -> Requirements: ...

    async def open_requests(self, customer_number: str) -> list[OpenRequest]:
        """A customer with no open requests gives []."""
        ...
