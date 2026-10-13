"""The bank's systems, as the pack's MCP servers reach them.

`build(mode)` gives the clients for a deployment: `fake` (in-memory seed data, for development,
tests and evals) or `real` (the bank's own systems over HTTP). The real clients are configured
by JUTANT_CORE_BANKING_*, JUTANT_SERVICE_CATALOG_*, JUTANT_LENDING_* and JUTANT_CARDS_*
variables (see `http.Connection`). Account services (holds, mandates, charges, standing orders,
cheques) and customer records (KYC) are usually the core banking system's, so they use its
connection; a bank that keeps them elsewhere gives them their own prefix here.
"""

import os
from dataclasses import dataclass

from packs.banking.adapters.base import (
    AccountServicesClient,
    CardsClient,
    CoreBankingClient,
    CustomerRecordsClient,
    LendingClient,
    ServiceCatalogClient,
    TransactionSource,
)
from packs.banking.adapters.core_banking_source import CoreBankingTransactions

# The channels core banking records, until the bank says (questionnaire: "Channels").
CORE_CHANNELS = frozenset({"branch"})


@dataclass(frozen=True)
class BankSystems:
    banking: CoreBankingClient
    catalog: ServiceCatalogClient
    accounts: AccountServicesClient
    customers: CustomerRecordsClient
    lending: LendingClient
    cards: CardsClient
    transactions: tuple[TransactionSource, ...] = ()  # every system that records transactions


def build(mode: str | None = None) -> BankSystems:
    """`mode` defaults to the JUTANT_BANKING_ADAPTERS environment variable, then `fake`."""
    mode = mode or os.environ.get("JUTANT_BANKING_ADAPTERS", "fake")
    if mode == "fake":
        from packs.banking.adapters.fake import FakeCoreBanking, FakeServiceCatalog
        from packs.banking.adapters.fake_accounts import FakeAccountServices, FakeCustomerRecords
        from packs.banking.adapters.fake_cards import FakeCards
        from packs.banking.adapters.fake_lending import FakeLending

        banking = FakeCoreBanking()
        return BankSystems(
            banking,
            FakeServiceCatalog(),
            FakeAccountServices(),
            FakeCustomerRecords(),
            FakeLending(),
            FakeCards(),
            (CoreBankingTransactions(banking, CORE_CHANNELS),),
        )
    if mode == "real":
        from packs.banking.adapters.account_services import (
            HttpAccountServicesClient,
            HttpCustomerRecordsClient,
        )
        from packs.banking.adapters.cards import HttpCardsClient
        from packs.banking.adapters.core_banking import HttpCoreBankingClient
        from packs.banking.adapters.http import BankHttp, Connection
        from packs.banking.adapters.lending import HttpLendingClient
        from packs.banking.adapters.service_catalog import HttpServiceCatalogClient

        core_http = BankHttp(Connection.from_env("JUTANT_CORE_BANKING"))
        core = HttpCoreBankingClient(core_http)
        return BankSystems(
            core,
            HttpServiceCatalogClient(BankHttp(Connection.from_env("JUTANT_SERVICE_CATALOG"))),
            HttpAccountServicesClient(core_http),
            HttpCustomerRecordsClient(core_http),
            HttpLendingClient(BankHttp(Connection.from_env("JUTANT_LENDING"))),
            HttpCardsClient(BankHttp(Connection.from_env("JUTANT_CARDS"))),
            (CoreBankingTransactions(core, CORE_CHANNELS),),
        )
    raise ValueError(f"JUTANT_BANKING_ADAPTERS must be 'fake' or 'real', not {mode!r}")
