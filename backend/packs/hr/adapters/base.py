"""Interfaces for the HR systems. The MCP tools depend on these, so a real client and the
dummy HR system can be swapped without changing the tools.

Three systems, as most organisations have them: employee records (the HRIS), leave
management, and the HR help desk. One product may hold all three; then one client implements
all three interfaces.

Every call is for one employee, by staff number, taken from the signed caller: no tool lets
anyone name another employee. Writes carry a `request_id` (the proposal's id) so a system that
receives the same request twice does it once.

Conventions: dates are ISO (YYYY-MM-DD), references upper case, days a decimal string ("5",
"0.5").
"""

from typing import Literal, Protocol, TypedDict


class NotFound(LookupError):
    """The record does not exist, or is not the employee's. Tools report it as `not_found`."""


class HrUnavailable(Exception):
    """The HR system could not be reached or answered with an error. Tools report it as
    `upstream_error`; the message is for the logs, never shown to the employee."""


class Employee(TypedDict):
    staff_number: str
    name: str
    job_title: str
    department: str
    location: str  # the office: public holidays and some rules depend on it
    manager: str  # the line manager's name: leave requests go to them
    grade: str
    employment_type: Literal["permanent", "fixed_term", "contractor"]
    start_date: str


class LeaveBalance(TypedDict):
    leave_type: str  # annual, sick...
    title: str  # Annual leave
    entitled: str  # days this year
    taken: str
    booked: str  # approved or waiting, not yet taken
    remaining: str  # entitled - taken - booked


class LeaveType(TypedDict):
    leave_type: str
    title: str
    counted: bool  # whether it uses a balance (annual) or not (unpaid)
    past_dates: bool  # whether it may be for days already gone (sick leave, recorded after)
    notice_days: int  # how far ahead it must be asked for
    evidence: str  # what must be given, if anything: "A doctor's note after 2 days"


class Holiday(TypedDict):
    date: str
    name: str


class LeaveRequest(TypedDict):
    reference: str  # LV-2026-00318
    leave_type: str
    start: str
    end: str
    days: str
    status: Literal["waiting", "approved", "declined", "cancelled", "taken"]
    approver: str
    submitted: str


class HelpRequest(TypedDict):
    reference: str  # HR-2026-00421
    category: str
    subject: str
    status: Literal["open", "in_progress", "waiting_for_you", "resolved", "closed"]
    team: str  # the queue it is with: Payroll Support
    opened: str
    updated: str
    confidential: bool  # its subject and comments are shown only to the employee and HR


class Comment(TypedDict):
    by: str  # "you" or the HR team's name
    at: str
    text: str


class Submitted(TypedDict):
    reference: str
    status: str  # in the employee's words: "Waiting for Ama Mensah"


class HrRecordsClient(Protocol):
    async def get_employee(self, staff_number: str) -> Employee: ...


class LeaveClient(Protocol):
    async def balances(self, staff_number: str, year: int) -> list[LeaveBalance]: ...
    async def leave_types(self) -> list[LeaveType]: ...
    async def holidays(self, location: str, year: int) -> list[Holiday]: ...
    async def leave_requests(self, staff_number: str) -> list[LeaveRequest]: ...
    async def submit(
        self,
        staff_number: str,
        leave_type: str,
        start: str,
        end: str,
        days: str,
        request_id: str,
    ) -> Submitted: ...


class HelpdeskClient(Protocol):
    async def help_requests(self, staff_number: str) -> list[HelpRequest]: ...
    async def get_request(self, staff_number: str, reference: str) -> HelpRequest: ...
    async def comments(self, staff_number: str, reference: str) -> list[Comment]: ...
    async def create(
        self,
        staff_number: str,
        category: str,
        subject: str,
        description: str,
        request_id: str,
        confidential: bool = False,
    ) -> Submitted: ...
    async def add_comment(
        self, staff_number: str, reference: str, text: str, request_id: str
    ) -> Submitted: ...
