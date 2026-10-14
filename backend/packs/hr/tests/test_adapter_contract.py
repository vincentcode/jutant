"""The real HTTP clients against the mock HR service: they read and write exactly what the
dummy system does, so swapping `fake` for `real` changes nothing the tools see."""

from datetime import date

import httpx
import pytest

from packs.hr.adapters.base import HrUnavailable, NotFound
from packs.hr.adapters.fake import DummyHr
from packs.hr.adapters.http import HrHttp, HttpHelpdesk, HttpHrRecords, HttpLeave
from packs.hr.mock_hr import create_app

TODAY = date(2026, 10, 13)


def clients(token: str | None = None, sent_token: str = ""):
    transport = httpx.ASGITransport(app=create_app(token, DummyHr(today=TODAY)))
    http = HrHttp("http://hr.test", sent_token, transport=transport)
    return HttpHrRecords(http), HttpLeave(http), HttpHelpdesk(http)


async def test_reads_match_the_dummy_system() -> None:
    records, leave, helpdesk = clients()
    dummy = DummyHr(today=TODAY)
    assert await records.get_employee("e1001") == await dummy.get_employee("E1001")
    assert await leave.balances("E1001", 2026) == await dummy.balances("E1001", 2026)
    assert await leave.leave_types() == await dummy.leave_types()
    assert await leave.holidays("Accra Head Office", 2026) == await dummy.holidays("", 2026)
    assert await helpdesk.help_requests("E1001") == await dummy.help_requests("E1001")
    assert await helpdesk.comments("E1001", "HR-2026-00419") == await dummy.comments(
        "E1001", "HR-2026-00419"
    )


async def test_writes_are_done_once_per_request_id() -> None:
    _, leave, helpdesk = clients()
    first = await leave.submit("E1001", "annual", "2026-11-09", "2026-11-13", "5", "r-1")
    again = await leave.submit("E1001", "annual", "2026-11-09", "2026-11-13", "5", "r-1")
    assert first == again and first["reference"] == "LV-2026-00290"
    assert len(await leave.leave_requests("E1001")) == 2
    made = await helpdesk.create("E1001", "documents", "Letter", "A letter for my landlord", "r-2")
    noted = await helpdesk.add_comment("E1001", made["reference"], "By Friday please", "r-3")
    assert noted["reference"] == made["reference"]


async def test_another_employees_request_is_not_found() -> None:
    _, _, helpdesk = clients()
    with pytest.raises(NotFound):
        await helpdesk.get_request("E1002", "HR-2026-00419")


async def test_a_wrong_token_is_an_unavailable_system_not_a_crash() -> None:
    records, _, _ = clients(token="right", sent_token="wrong")
    with pytest.raises(HrUnavailable):
        await records.get_employee("E1001")
    records, _, _ = clients(token="right", sent_token="right")
    assert (await records.get_employee("E1001"))["name"] == "Abena Owusu"
