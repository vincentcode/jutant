"""The HR server's tools: an employee's own HR record, leave and HR requests, and the
proposals and submissions of confirmed actions (`core.actions`).

Every tool is for the caller only: the staff number is the signed caller's, never an argument,
so no question can reach another employee's record. Facts are assembled in code (`domain`).

The `propose_*` tools check a request and return the card to show; they change nothing. The
`submit_*` tools do it, and no feature lists them: only the platform calls them, once the
employee presses Send, with the card's arguments and `request_id`.
"""

from collections.abc import Callable
from datetime import date

from core.policy.engine import PolicyEngine
from core.types import Caller, Citation
from mcp_servers.common.guard import GuardedServer, ToolInputError, ToolOutput
from packs.hr.adapters.base import Employee, HelpdeskClient, HrRecordsClient, LeaveClient
from packs.hr.domain import leave as leave_rules
from packs.hr.domain import requests as request_rules

PROFILE_FIELDS = (
    "name",
    "job_title",
    "department",
    "location",
    "manager",
    "employment_type",
    "start_date",
)


def create_server(
    records: HrRecordsClient,
    leave: LeaveClient,
    helpdesk: HelpdeskClient,
    engine: PolicyEngine,
    secret: str,
    today: Callable[[], date] = date.today,
) -> GuardedServer:
    server = GuardedServer("hr", engine, secret)

    def mine(caller: Caller, title: str) -> tuple[Citation, ...]:
        return (Citation("record", title, caller.id),)

    # --- reading --------------------------------------------------------------------------------

    @server.tool(
        "my_profile",
        "Your HR record: job title, department, office, manager, employment type, start date.",
    )
    async def my_profile(caller: Caller) -> ToolOutput:
        employee = await records.get_employee(caller.id)
        data = {k.replace("_", " "): str(employee[k]) for k in PROFILE_FIELDS}  # type: ignore[literal-required]
        return ToolOutput(data=data, citations=mine(caller, "HR record"))

    @server.tool(
        "leave_balance",
        "Your leave this year: days left, taken and booked of each kind, and the leave you "
        "have asked for or that is approved.",
    )
    async def leave_balance(caller: Caller) -> ToolOutput:
        year = today().year
        balances = await leave.balances(caller.id, year)
        requests = await leave.leave_requests(caller.id)
        return ToolOutput(
            data=leave_rules.balance_facts(year, balances, requests),
            citations=mine(caller, "Leave balance"),
        )

    @server.tool(
        "leave_types",
        "The kinds of leave: whether each uses a balance, the notice it needs, and what must "
        "be given with it.",
    )
    async def leave_types(caller: Caller) -> ToolOutput:
        kinds = await leave.leave_types()
        data = [
            {
                "kind": k["title"],
                "uses a balance": "yes" if k["counted"] else "no",
                "notice": f"{k['notice_days']} days" if k["notice_days"] else "none",
                "may be for days already gone": "yes" if k["past_dates"] else "no",
                "needs": k["evidence"] or "nothing",
            }
            for k in kinds
        ]
        return ToolOutput(data=data, citations=(Citation("record", "Leave types", "all"),))

    @server.tool("holidays", "Public holidays at your office this year and next.")
    async def holidays(caller: Caller) -> ToolOutput:
        employee = await records.get_employee(caller.id)
        year = today().year
        days = [
            *await leave.holidays(employee["location"], year),
            *await leave.holidays(employee["location"], year + 1),
        ]
        data = [
            {"date": leave_rules.day(h["date"]), "holiday": h["name"]}
            for h in days
            if h["date"] >= today().isoformat()
        ]
        return ToolOutput(
            data=data, citations=(Citation("record", "Public holidays", employee["location"]),)
        )

    @server.tool("my_requests", "Your HR requests and leave requests, and where each stands.")
    async def my_requests(caller: Caller) -> ToolOutput:
        tickets = await helpdesk.help_requests(caller.id)
        leave_lines = [
            f"{r['reference']}: {leave_rules.TITLES.get(r['leave_type'], r['leave_type'])}, "
            f"{leave_rules.span(r['start'], r['end'])}, {r['status']}"
            for r in await leave.leave_requests(caller.id)
        ]
        return ToolOutput(
            data=request_rules.listing(leave_lines, tickets),
            citations=mine(caller, "HR requests"),
        )

    @server.tool(
        "get_request",
        "One of your HR requests by its reference (HR-2026-00421): where it stands and the "
        "latest update.",
    )
    async def get_request(caller: Caller, reference: str) -> ToolOutput:
        number = reference.strip().upper()
        request = await helpdesk.get_request(caller.id, number)
        comments = [] if request["confidential"] else await helpdesk.comments(caller.id, number)
        return ToolOutput(
            data=request_rules.details(request, comments),
            citations=(Citation("record", "HR request", number),),
        )

    # --- proposing: nothing changes until the employee sends the card --------------------------

    @server.tool(
        "propose_leave_request",
        "Check a leave request and prepare it for you to send. `dates` is start/end "
        "(YYYY-MM-DD/YYYY-MM-DD). Nothing is sent.",
    )
    async def propose_leave_request(caller: Caller, leave_type: str, dates: str) -> ToolOutput:
        employee = await records.get_employee(caller.id)
        checked = await _check_leave(caller.id, employee, leave_type, dates)
        data = checked.draft if checked.draft is not None else {"refused": checked.refused}
        return ToolOutput(data=data, citations=mine(caller, "Leave balance"))

    async def _check_leave(
        staff: str, employee: Employee, leave_type: str, dates: str
    ) -> leave_rules.Check:
        kinds = {k["leave_type"]: k for k in await leave.leave_types()}
        kind = kinds.get(leave_type.strip().lower())
        start_year = int(dates[:4]) if dates[:4].isdigit() else today().year
        balances = {b["leave_type"]: b for b in await leave.balances(staff, start_year)}
        holidays_ = [
            *await leave.holidays(employee["location"], start_year),
            *await leave.holidays(employee["location"], start_year + 1),
        ]
        return leave_rules.check(
            today=today(),
            employee=employee,
            kind=kind,
            balance=balances.get(kind["leave_type"]) if kind else None,
            period=dates.strip(),
            holidays=holidays_,
            requests=await leave.leave_requests(staff),
        )

    @server.tool(
        "propose_help_request",
        "Prepare a new HR request for you to send: its kind (payroll, leave, benefits, "
        "documents, policy, other) and what it is about. Nothing is sent.",
    )
    async def propose_help_request(caller: Caller, category: str, description: str) -> ToolOutput:
        data = request_rules.new_request(category.strip().lower(), description)
        return ToolOutput(data=data, citations=mine(caller, "HR requests"))

    @server.tool(
        "propose_comment",
        "Prepare something to add to one of your HR requests, for you to send. Nothing is sent.",
    )
    async def propose_comment(caller: Caller, reference: str, comment: str) -> ToolOutput:
        number = reference.strip().upper()
        request = await helpdesk.get_request(caller.id, number)
        return ToolOutput(
            data=request_rules.comment(request, comment),
            citations=(Citation("record", "HR request", number),),
        )

    @server.tool(
        "propose_contact",
        "Prepare a request for HR to contact you: `private` for something sensitive, "
        "`general` otherwise. Nothing you wrote is included. Nothing is sent.",
    )
    async def propose_contact(caller: Caller, kind: str) -> ToolOutput:
        return ToolOutput(
            data=request_rules.contact(kind.strip().lower()),
            citations=(Citation("record", "HR contact", "Employee Relations"),),
        )

    # --- submitting: only the platform calls these, once the employee confirms ------------------

    @server.tool("submit_leave_request", "Send a leave request the employee confirmed.")
    async def submit_leave_request(
        caller: Caller, leave_type: str, start: str, end: str, request_id: str
    ) -> ToolOutput:
        employee = await records.get_employee(caller.id)
        # Sent before (a retry after no answer): that request, not a second one.
        for r in await leave.leave_requests(caller.id):
            if (r["leave_type"], r["start"], r["end"]) == (leave_type, start, end) and r[
                "status"
            ] in leave_rules.OPEN:
                done = {"reference": r["reference"], "status": leave_rules.status_of(r)}
                return ToolOutput(data=done, citations=mine(caller, "Leave request"))
        checked = await _check_leave(caller.id, employee, leave_type, f"{start}/{end}")
        if checked.draft is None:  # the balance changed since the card was shown
            raise ToolInputError(checked.refused)
        days = next(f["value"] for f in checked.draft["fields"] if f["label"] == "Days")
        done = await leave.submit(caller.id, leave_type, start, end, days.split()[0], request_id)
        return ToolOutput(data=done, citations=mine(caller, "Leave request"))

    @server.tool("submit_help_request", "Send an HR request the employee confirmed.")
    async def submit_help_request(
        caller: Caller, category: str, subject: str, description: str, request_id: str
    ) -> ToolOutput:
        if category not in request_rules.CATEGORIES:
            raise ToolInputError(f"unknown category {category}")
        done = await helpdesk.create(caller.id, category, subject, description, request_id)
        return ToolOutput(data=done, citations=mine(caller, "HR request"))

    @server.tool("submit_comment", "Add to an HR request what the employee confirmed.")
    async def submit_comment(
        caller: Caller, reference: str, comment: str, request_id: str
    ) -> ToolOutput:
        done = await helpdesk.add_comment(caller.id, reference.strip().upper(), comment, request_id)
        return ToolOutput(data=done, citations=mine(caller, "HR request"))

    @server.tool("submit_contact", "Ask HR to contact the employee, as they confirmed.")
    async def submit_contact(caller: Caller, kind: str, request_id: str) -> ToolOutput:
        if kind not in request_rules.CONTACT:
            raise ToolInputError(f"unknown kind {kind}")
        private = kind == "private"
        done = await helpdesk.create(
            caller.id,
            "confidential" if private else "other",
            "Asked to talk to HR privately" if private else "Asked to talk to someone in HR",
            "",
            request_id,
            confidential=private,
        )
        return ToolOutput(data=done, citations=mine(caller, "HR request"))

    return server
