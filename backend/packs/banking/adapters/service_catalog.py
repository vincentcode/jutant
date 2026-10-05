"""Real service catalogue client.

PROVISIONAL: the bank has not yet said what its catalogue exposes, so this client speaks a
plain REST interface of our own (served for development by `packs/banking/mock_bank.py`):

    GET /products?q=
    GET /products/{code}
    GET /requirements/{request_type}
    GET /customers/{customer_number}/requests?status=open

When the bank's interface is known, change the paths in the methods and the `to_*` functions
that map its responses to the records in `base.py`. Nothing outside this file needs to change;
`tests/test_adapter_contract.py` shows whether the result still keeps the contract.
"""

from typing import Any

from packs.banking.adapters.base import OpenRequest, Product, ProductMatch, Requirements
from packs.banking.adapters.http import BankHttp, mapped, money, segment


class HttpServiceCatalogClient:
    def __init__(self, http: BankHttp):
        self.http = http

    async def search_products(self, query: str) -> list[ProductMatch]:
        raw = await self.http.get("/products", {"q": query})
        return mapped(lambda items: [to_product_match(p) for p in items], raw, "product list")

    async def get_product(self, code: str) -> Product:
        raw = await self.http.get(f"/products/{segment(code)}")
        return mapped(to_product, raw, "product")

    async def get_requirements(self, request_type: str) -> Requirements:
        raw = await self.http.get(f"/requirements/{segment(request_type)}")
        return mapped(to_requirements, raw, "requirements")

    async def open_requests(self, customer_number: str) -> list[OpenRequest]:
        raw = await self.http.get(
            f"/customers/{segment(customer_number)}/requests", {"status": "open"}
        )
        return mapped(lambda items: [to_open_request(r) for r in items], raw, "request list")


def to_product_match(raw: dict[str, Any]) -> ProductMatch:
    return {"code": str(raw["code"]).upper(), "name": str(raw["name"])}


def to_product(raw: dict[str, Any]) -> Product:
    return {
        "code": str(raw["code"]).upper(),
        "name": str(raw["name"]),
        "rate": str(raw["rate"]),
        "fees": {str(k): money(v) for k, v in (raw.get("fees") or {}).items()},
        "eligibility": str(raw.get("eligibility") or ""),
        "required_documents": [str(d) for d in raw.get("required_documents") or []],
    }


def to_requirements(raw: dict[str, Any]) -> Requirements:
    return {
        "request_type": str(raw["request_type"]),
        "forms": [str(f) for f in raw.get("forms") or []],
        "signatures": [str(s) for s in raw.get("signatures") or []],
        "approvals": [str(a) for a in raw.get("approvals") or []],
    }


def to_open_request(raw: dict[str, Any]) -> OpenRequest:
    request: OpenRequest = {
        "id": str(raw["id"]),
        "type": str(raw["type"]),
        "status": str(raw["status"]),
    }
    if raw.get("opened"):
        request["opened"] = str(raw["opened"])[:10]
    return request
