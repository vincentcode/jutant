"""Real core banking client. Written once the bank states what its system exposes;
until then the pack runs on the fakes in `fake.py`."""

from typing import Any


class HttpCoreBankingClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_account(self, account_number: str) -> dict[str, Any]:
        raise NotImplementedError

    async def list_transactions(self, account_number: str, **filters: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_transaction(self, reference: str) -> dict[str, Any]:
        raise NotImplementedError

    async def get_customer(self, customer_number: str) -> dict[str, Any]:
        raise NotImplementedError
