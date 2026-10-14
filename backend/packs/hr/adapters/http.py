"""HTTP clients for the HR systems, over a provisional interface (`packs.hr.mock_hr` serves it).

When the organisation's HR products are known, these clients change to speak their APIs and map
the answers into the records of `base`; the tools do not change. Each system is configured by
JUTANT_HR_<SYSTEM>_URL and, if it needs one, JUTANT_HR_<SYSTEM>_TOKEN (a bearer token), with
<SYSTEM> one of RECORDS, LEAVE and HELPDESK; a product that holds all three is given the same
URL for each.

Reads are retried once on a connection failure or a 5xx. Writes are not retried here: the
platform keeps the request waiting to be sent again, with the same `request_id`, so the system
does it once.
"""

import os
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import quote

import httpx

from packs.hr.adapters.base import (
    Comment,
    Employee,
    HelpRequest,
    Holiday,
    HrUnavailable,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    NotFound,
    Submitted,
)


class HrHttp:
    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s, transport=transport
        )

    @classmethod
    def from_env(cls, system: str, env: Mapping[str, str] = os.environ) -> "HrHttp":
        prefix = f"JUTANT_HR_{system}"
        url = env.get(f"{prefix}_URL", "").strip()
        if not url:
            raise ValueError(f"{prefix}_URL is not set")
        return cls(url, env.get(f"{prefix}_TOKEN", "").strip())

    async def get(self, path: str, **params: Any) -> Any:
        for attempt in (1, 2):
            try:
                response = await self.client.get(path, params=params or None)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise HrUnavailable(f"GET {path}: {exc}") from exc
                continue
            if response.status_code >= 500 and attempt == 1:
                continue
            return _body(response, f"GET {path}")
        raise HrUnavailable(f"GET {path}: no answer")  # pragma: no cover

    async def post(self, path: str, body: dict[str, Any]) -> Any:
        try:
            response = await self.client.post(path, json=body)
        except httpx.TransportError as exc:
            raise HrUnavailable(f"POST {path}: {exc}") from exc
        return _body(response, f"POST {path}")


def _body(response: httpx.Response, what: str) -> Any:
    if response.status_code == 404:
        raise NotFound(what)
    if response.status_code >= 400:
        raise HrUnavailable(f"{what}: HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise HrUnavailable(f"{what}: not JSON") from exc


def _q(value: str) -> str:
    return quote(value.strip().upper(), safe="")


class HttpHrRecords:
    def __init__(self, http: HrHttp):
        self.http = http

    async def get_employee(self, staff_number: str) -> Employee:
        return cast(Employee, await self.http.get(f"/employees/{_q(staff_number)}"))


class HttpLeave:
    def __init__(self, http: HrHttp):
        self.http = http

    async def balances(self, staff_number: str, year: int) -> list[LeaveBalance]:
        found = await self.http.get(f"/employees/{_q(staff_number)}/leave/balances", year=year)
        return cast(list[LeaveBalance], found)

    async def leave_types(self) -> list[LeaveType]:
        return cast(list[LeaveType], await self.http.get("/leave/types"))

    async def holidays(self, location: str, year: int) -> list[Holiday]:
        return cast(list[Holiday], await self.http.get("/holidays", location=location, year=year))

    async def leave_requests(self, staff_number: str) -> list[LeaveRequest]:
        found = await self.http.get(f"/employees/{_q(staff_number)}/leave/requests")
        return cast(list[LeaveRequest], found)

    async def submit(
        self, staff_number: str, leave_type: str, start: str, end: str, days: str, request_id: str
    ) -> Submitted:
        body = {
            "leave_type": leave_type,
            "start": start,
            "end": end,
            "days": days,
            "request_id": request_id,
        }
        found = await self.http.post(f"/employees/{_q(staff_number)}/leave/requests", body)
        return cast(Submitted, found)


class HttpHelpdesk:
    def __init__(self, http: HrHttp):
        self.http = http

    async def help_requests(self, staff_number: str) -> list[HelpRequest]:
        return cast(
            list[HelpRequest], await self.http.get(f"/employees/{_q(staff_number)}/requests")
        )

    async def get_request(self, staff_number: str, reference: str) -> HelpRequest:
        path = f"/employees/{_q(staff_number)}/requests/{_q(reference)}"
        return cast(HelpRequest, await self.http.get(path))

    async def comments(self, staff_number: str, reference: str) -> list[Comment]:
        path = f"/employees/{_q(staff_number)}/requests/{_q(reference)}/comments"
        return cast(list[Comment], await self.http.get(path))

    async def create(
        self,
        staff_number: str,
        category: str,
        subject: str,
        description: str,
        request_id: str,
        confidential: bool = False,
    ) -> Submitted:
        body = {
            "category": category,
            "subject": subject,
            "description": description,
            "request_id": request_id,
            "confidential": confidential,
        }
        return cast(
            Submitted, await self.http.post(f"/employees/{_q(staff_number)}/requests", body)
        )

    async def add_comment(
        self, staff_number: str, reference: str, text: str, request_id: str
    ) -> Submitted:
        path = f"/employees/{_q(staff_number)}/requests/{_q(reference)}/comments"
        return cast(Submitted, await self.http.post(path, {"text": text, "request_id": request_id}))
