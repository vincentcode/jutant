"""A stand-in for the HR systems: the dummy HR system over HTTP.

It serves the provisional interface the clients in `adapters/http.py` speak, so the pack can
run with JUTANT_HR_ADAPTERS=real before the organisation's HR systems are reachable, and the
contract test can run the real clients over HTTP. Its state lives as long as the process.

Run: python -m packs.hr.mock_hr    (port JUTANT_MOCK_HR_PORT, default 8191)

If JUTANT_MOCK_HR_TOKEN is set, every request needs `Authorization: Bearer <token>`.
"""

import os
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from packs.hr.adapters.base import NotFound
from packs.hr.adapters.fake import DummyHr

Handler = Callable[[Request], Awaitable[Any]]


def create_app(token: str | None = None, hr: DummyHr | None = None) -> Starlette:
    hr = hr or DummyHr()

    def endpoint(handler: Handler) -> Callable[[Request], Awaitable[JSONResponse]]:
        async def respond(request: Request) -> JSONResponse:
            if token and request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "unauthorised"}, status_code=401)
            try:
                return JSONResponse(await handler(request))
            except NotFound:
                return JSONResponse({"error": "not found"}, status_code=404)

        return respond

    async def employee(request: Request) -> Any:
        return await hr.get_employee(request.path_params["number"])

    async def balances(request: Request) -> Any:
        year = int(request.query_params["year"])
        return await hr.balances(request.path_params["number"], year)

    async def leave_types(request: Request) -> Any:
        return await hr.leave_types()

    async def holidays(request: Request) -> Any:
        query = request.query_params
        return await hr.holidays(query.get("location", ""), int(query["year"]))

    async def leave_requests(request: Request) -> Any:
        number = request.path_params["number"]
        if request.method == "POST":
            body = await request.json()
            return await hr.submit(
                number,
                body["leave_type"],
                body["start"],
                body["end"],
                body["days"],
                body["request_id"],
            )
        return await hr.leave_requests(number)

    async def help_requests(request: Request) -> Any:
        number = request.path_params["number"]
        if request.method == "POST":
            body = await request.json()
            return await hr.create(
                number,
                body["category"],
                body["subject"],
                body["description"],
                body["request_id"],
                bool(body.get("confidential")),
            )
        return await hr.help_requests(number)

    async def help_request(request: Request) -> Any:
        params = request.path_params
        return await hr.get_request(params["number"], params["reference"])

    async def comments(request: Request) -> Any:
        params = request.path_params
        if request.method == "POST":
            body = await request.json()
            return await hr.add_comment(
                params["number"], params["reference"], body["text"], body["request_id"]
            )
        return await hr.comments(params["number"], params["reference"])

    both = ["GET", "POST"]
    return Starlette(
        routes=[
            Route("/employees/{number}", endpoint(employee)),
            Route("/employees/{number}/leave/balances", endpoint(balances)),
            Route("/employees/{number}/leave/requests", endpoint(leave_requests), methods=both),
            Route("/employees/{number}/requests", endpoint(help_requests), methods=both),
            Route("/employees/{number}/requests/{reference}", endpoint(help_request)),
            Route(
                "/employees/{number}/requests/{reference}/comments",
                endpoint(comments),
                methods=both,
            ),
            Route("/leave/types", endpoint(leave_types)),
            Route("/holidays", endpoint(holidays)),
        ]
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        create_app(os.environ.get("JUTANT_MOCK_HR_TOKEN") or None),
        host=os.environ.get("JUTANT_MOCK_HR_HOST", "0.0.0.0"),
        port=int(os.environ.get("JUTANT_MOCK_HR_PORT", "8191")),
    )
