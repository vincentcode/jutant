"""The HR tools through the real guard and the pack's own rules, on the dummy HR system."""

from contextlib import asynccontextmanager
from datetime import date

from core.packs.loader import load_pack
from core.policy.engine import PolicyEngine
from core.types import Caller, ToolCall
from packs.hr.adapters.fake import DummyHr
from packs.hr.mcp_servers import PACK_DIR
from packs.hr.mcp_servers.hr.tools import create_server
from providers.mcp.client import McpToolClient

SECRET = "s3cret"
TODAY = date(2026, 10, 13)


def employee(staff_number: str = "E1001") -> Caller:
    return Caller(staff_number, "employee", "staff")


@asynccontextmanager
async def hr_server(hr: DummyHr | None = None):
    pack = load_pack(PACK_DIR)
    hr = hr or DummyHr(today=TODAY)
    server = create_server(
        hr, hr, hr, PolicyEngine(pack.rules, pack.field_rules), SECRET, today=lambda: TODAY
    )
    async with McpToolClient({"hr": server.mcp}, SECRET) as client:

        async def call(tool: str, caller: Caller | None = None, **arguments):
            return await client.call(caller or employee(), ToolCall("1", f"hr.{tool}", arguments))

        yield call


async def test_the_profile_is_the_callers_own_without_grade() -> None:
    async with hr_server() as call:
        result = await call("my_profile")
    assert result.data["manager"] == "Kofi Mensah"
    assert "grade" not in result.data
    assert result.citations[0].locator == "E1001"


async def test_the_balance_is_set_out_in_code() -> None:
    async with hr_server() as call:
        result = await call("leave_balance")
    assert result.data["Annual leave"] == "13 of 21 days left (8 taken, 0 booked)"
    assert result.data["leave requested or approved"] == "none"


async def test_a_proposal_changes_nothing_and_sending_it_does_once() -> None:
    async with hr_server() as call:
        draft = (
            await call("propose_leave_request", leave_type="annual", dates="2026-11-09/2026-11-13")
        ).data
        assert draft["summary"] == "Annual leave, 9-13 Nov 2026"
        assert (await call("leave_balance")).data["Annual leave"].startswith("13 of 21")

        arguments = {**draft["submit"], "request_id": "p-1"}
        sent = await call("submit_leave_request", **arguments)
        again = await call("submit_leave_request", **arguments)
        assert (
            sent.data
            == again.data
            == {"reference": "LV-2026-00290", "status": "Waiting for Kofi Mensah"}
        )

        balance = (await call("leave_balance")).data
        assert balance["Annual leave"] == "8 of 21 days left (8 taken, 5 booked)"
        assert "LV-2026-00290" in balance["leave requested or approved"]
        assert "LV-2026-00290" in (await call("my_requests")).data["leave requests"]


async def test_a_request_that_cannot_be_made_is_refused_with_the_reason() -> None:
    async with hr_server() as call:
        result = await call(
            "propose_leave_request", leave_type="annual", dates="2026-11-02/2026-11-27"
        )
    assert result.ok and "13 days of annual leave left" in result.data["refused"]
    assert "submit" not in result.data


async def test_sending_is_checked_again_in_case_the_balance_changed() -> None:
    hr = DummyHr(today=TODAY)
    async with hr_server(hr) as call:
        draft = (
            await call("propose_leave_request", leave_type="annual", dates="2026-11-09/2026-11-13")
        ).data
        hr.taken["E1001"]["annual"] = hr.taken["E1001"]["annual"] + 10  # taken elsewhere meanwhile
        refused = await call("submit_leave_request", **draft["submit"], request_id="p-2")
    assert refused.error == "invalid_arguments"


async def test_another_employees_request_does_not_exist_for_you() -> None:
    async with hr_server() as call:
        mine = await call("get_request", reference="HR-2026-00419")
        theirs = await call("get_request", employee("E1002"), reference="HR-2026-00419")
    assert mine.data["latest update"].startswith("2026-10-06, Payroll Support")
    assert theirs.error == "not_found"


async def test_a_help_request_needs_words_and_goes_to_the_right_team() -> None:
    async with hr_server() as call:
        short = await call("propose_help_request", category="payroll", description="Payroll")
        draft = (
            await call(
                "propose_help_request",
                category="payroll",
                description="My overtime for September is missing from my pay. Please check.",
            )
        ).data
        sent = await call("submit_help_request", **draft["submit"], request_id="p-3")
    assert "a sentence or two" in short.data["refused"]
    assert draft["summary"] == "My overtime for September is missing from my pay"
    assert sent.data == {"reference": "HR-2026-00421", "status": "With Payroll Support"}


async def test_asking_to_talk_privately_sends_nothing_written_and_stays_confidential() -> None:
    async with hr_server() as call:
        draft = (await call("propose_contact", kind="private")).data
        sent = (await call("submit_contact", **draft["submit"], request_id="p-4")).data
        shown = (await call("get_request", reference=sent["reference"])).data
        listed = (await call("my_requests")).data["help requests"]
    assert draft["submit"] == {"kind": "private"}
    assert sent["status"] == "With Employee Relations"
    assert "subject" not in shown and shown["confidential"].startswith("yes")
    assert f"{sent['reference']}: confidential" in listed


async def test_a_comment_is_added_to_ones_own_request() -> None:
    async with hr_server() as call:
        draft = (
            await call(
                "propose_comment", reference="hr-2026-00419", comment="The hours were 6 in total."
            )
        ).data
        sent = (await call("submit_comment", **draft["submit"], request_id="p-5")).data
    assert draft["summary"] == "Add to HR-2026-00419"
    assert sent["reference"] == "HR-2026-00419"


async def test_only_employees_may_use_the_tools() -> None:
    async with hr_server() as call:
        result = await call("leave_balance", Caller("S1", "teller", "staff"))
    assert result.error == "denied"
