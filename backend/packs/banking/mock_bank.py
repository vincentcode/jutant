"""A stand-in for the bank's systems: the fake bank's data over HTTP.

It serves the provisional interface the real clients in `adapters/` speak, so the pack can run
with JUTANT_BANKING_ADAPTERS=real before the bank's systems are reachable, and the contract
test can run the real clients over HTTP. When the bank's interface is known, change this to
answer as the bank's systems do (from their sample responses), alongside the clients.

Run: python -m packs.banking.mock_bank    (port JUTANT_MOCK_BANK_PORT, default 8190)

If JUTANT_MOCK_BANK_TOKEN is set, every request needs `Authorization: Bearer <token>`.
"""

import os
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from packs.banking.adapters.base import NotFound
from packs.banking.adapters.fake import FakeCoreBanking, FakeServiceCatalog

Handler = Callable[[Request], Awaitable[Any]]


def create_app(token: str | None = None) -> Starlette:
    banking, catalog = FakeCoreBanking(), FakeServiceCatalog()

    def endpoint(handler: Handler) -> Callable[[Request], Awaitable[JSONResponse]]:
        async def respond(request: Request) -> JSONResponse:
            if token and request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "unauthorised"}, status_code=401)
            try:
                return JSONResponse(await handler(request))
            except NotFound:
                return JSONResponse({"error": "not found"}, status_code=404)

        return respond

    async def account(request: Request) -> Any:
        return await banking.get_account(request.path_params["number"])

    async def transactions(request: Request) -> Any:
        query = request.query_params
        filters: dict[str, Any] = {"limit": int(query.get("limit", 5))}
        for name in ("from_date", "to_date", "direction"):
            if query.get(name):
                filters[name] = query[name]
        return await banking.list_transactions(request.path_params["number"], **filters)

    async def transaction(request: Request) -> Any:
        return await banking.get_transaction(request.path_params["reference"])

    async def customer(request: Request) -> Any:
        return await banking.get_customer(request.path_params["number"])

    async def products(request: Request) -> Any:
        return await catalog.search_products(request.query_params.get("q", ""))

    async def product(request: Request) -> Any:
        return await catalog.get_product(request.path_params["code"])

    async def requirements(request: Request) -> Any:
        return await catalog.get_requirements(request.path_params["request_type"])

    async def requests(request: Request) -> Any:
        return await catalog.open_requests(request.path_params["number"])

    return Starlette(
        routes=[
            Route("/accounts/{number}", endpoint(account)),
            Route("/accounts/{number}/transactions", endpoint(transactions)),
            Route("/transactions/{reference}", endpoint(transaction)),
            Route("/customers/{number}", endpoint(customer)),
            Route("/customers/{number}/requests", endpoint(requests)),
            Route("/products", endpoint(products)),
            Route("/products/{code}", endpoint(product)),
            Route("/requirements/{request_type}", endpoint(requirements)),
        ]
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        create_app(os.environ.get("JUTANT_MOCK_BANK_TOKEN") or None),
        host=os.environ.get("JUTANT_MOCK_BANK_HOST", "0.0.0.0"),
        port=int(os.environ.get("JUTANT_MOCK_BANK_PORT", "8190")),
    )
