"""Real service catalogue client. Written once the bank states what its system exposes;
until then the pack runs on the fakes in `fake.py`."""

from typing import Any


class HttpServiceCatalogClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def search_products(self, query: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_product(self, code: str) -> dict[str, Any]:
        raise NotImplementedError

    async def get_requirements(self, request_type: str) -> dict[str, Any]:
        raise NotImplementedError

    async def open_requests(self, customer_number: str) -> list[dict[str, Any]]:
        raise NotImplementedError
