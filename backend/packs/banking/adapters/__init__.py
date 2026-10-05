"""The bank's systems, as the pack's MCP servers reach them.

`build(mode)` gives the clients for a deployment: `fake` (in-memory seed data, for development,
tests and evals) or `real` (the bank's own systems over HTTP). The real clients are configured
by JUTANT_CORE_BANKING_* and JUTANT_SERVICE_CATALOG_* variables (see `http.Connection`).
"""

import os
from dataclasses import dataclass

from packs.banking.adapters.base import CoreBankingClient, ServiceCatalogClient


@dataclass(frozen=True)
class BankSystems:
    banking: CoreBankingClient
    catalog: ServiceCatalogClient


def build(mode: str | None = None) -> BankSystems:
    """`mode` defaults to the JUTANT_BANKING_ADAPTERS environment variable, then `fake`."""
    mode = mode or os.environ.get("JUTANT_BANKING_ADAPTERS", "fake")
    if mode == "fake":
        from packs.banking.adapters.fake import FakeCoreBanking, FakeServiceCatalog

        return BankSystems(FakeCoreBanking(), FakeServiceCatalog())
    if mode == "real":
        from packs.banking.adapters.core_banking import HttpCoreBankingClient
        from packs.banking.adapters.http import BankHttp, Connection
        from packs.banking.adapters.service_catalog import HttpServiceCatalogClient

        return BankSystems(
            HttpCoreBankingClient(BankHttp(Connection.from_env("JUTANT_CORE_BANKING"))),
            HttpServiceCatalogClient(BankHttp(Connection.from_env("JUTANT_SERVICE_CATALOG"))),
        )
    raise ValueError(f"JUTANT_BANKING_ADAPTERS must be 'fake' or 'real', not {mode!r}")
