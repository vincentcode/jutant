"""The dummy HR system: employee records, leave and an HR help desk, in memory.

It stands in until the organisation's HR systems are known (`docs/hr-design.md`). One object
implements all three interfaces over shared state, so a leave request filed is then listed with
the employee's requests and counted in their balance.

Anyone who signs in has a record: a staff number it does not know gets a default one, made the
first time it is asked for, so the pack works with whatever accounts the deployment has. The
seeded employees (E1001, E1002) have history to ask about.

All data is sample data.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from packs.hr.adapters.base import (
    Comment,
    Employee,
    HelpRequest,
    Holiday,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    NotFound,
    Submitted,
)

LEAVE_TYPES: list[LeaveType] = [
    {
        "leave_type": "annual",
        "title": "Annual leave",
        "counted": True,
        "past_dates": False,
        "notice_days": 3,
        "evidence": "",
    },
    {
        "leave_type": "sick",
        "title": "Sick leave",
        "counted": True,
        "past_dates": True,
        "notice_days": 0,
        "evidence": "A doctor's note for more than 2 days in a row",
    },
    {
        "leave_type": "compassionate",
        "title": "Compassionate leave",
        "counted": True,
        "past_dates": True,
        "notice_days": 0,
        "evidence": "",
    },
    {
        "leave_type": "study",
        "title": "Study leave",
        "counted": True,
        "past_dates": False,
        "notice_days": 14,
        "evidence": "The exam timetable",
    },
    {
        "leave_type": "maternity",
        "title": "Maternity leave",
        "counted": False,
        "past_dates": False,
        "notice_days": 30,
        "evidence": "A medical certificate of the due date",
    },
    {
        "leave_type": "paternity",
        "title": "Paternity leave",
        "counted": True,
        "past_dates": True,
        "notice_days": 0,
        "evidence": "The child's birth certificate",
    },
    {
        "leave_type": "unpaid",
        "title": "Unpaid leave",
        "counted": False,
        "past_dates": False,
        "notice_days": 14,
        "evidence": "",
    },
]
ENTITLED = {"annual": 21, "sick": 10, "compassionate": 5, "study": 5, "paternity": 5}

# Public holidays at the Accra offices (SAMPLE: confirm each year's list with HR).
HOLIDAYS: dict[int, list[Holiday]] = {
    2026: [
        {"date": "2026-01-01", "name": "New Year's Day"},
        {"date": "2026-01-07", "name": "Constitution Day"},
        {"date": "2026-03-06", "name": "Independence Day"},
        {"date": "2026-04-03", "name": "Good Friday"},
        {"date": "2026-04-06", "name": "Easter Monday"},
        {"date": "2026-05-01", "name": "May Day"},
        {"date": "2026-07-01", "name": "Republic Day"},
        {"date": "2026-08-04", "name": "Founders' Day"},
        {"date": "2026-09-21", "name": "Kwame Nkrumah Memorial Day"},
        {"date": "2026-12-04", "name": "Farmers' Day"},
        {"date": "2026-12-25", "name": "Christmas Day"},
        {"date": "2026-12-26", "name": "Boxing Day"},
    ],
    2027: [
        {"date": "2027-01-01", "name": "New Year's Day"},
        {"date": "2027-01-07", "name": "Constitution Day"},
        {"date": "2027-03-06", "name": "Independence Day"},
        {"date": "2027-03-26", "name": "Good Friday"},
        {"date": "2027-03-29", "name": "Easter Monday"},
        {"date": "2027-05-01", "name": "May Day"},
        {"date": "2027-07-01", "name": "Republic Day"},
        {"date": "2027-08-04", "name": "Founders' Day"},
        {"date": "2027-09-21", "name": "Kwame Nkrumah Memorial Day"},
        {"date": "2027-12-03", "name": "Farmers' Day"},
        {"date": "2027-12-25", "name": "Christmas Day"},
        {"date": "2027-12-26", "name": "Boxing Day"},
    ],
}

# Where each kind of help request goes.
TEAMS = {
    "payroll": "Payroll Support",
    "leave": "Leave Administration",
    "benefits": "Benefits",
    "documents": "HR Documents",
    "policy": "HR Advisory",
    "confidential": "Employee Relations",
    "other": "HR Service Desk",
}

EMPLOYEES: dict[str, Employee] = {
    "E1001": {
        "staff_number": "E1001",
        "name": "Abena Owusu",
        "job_title": "Relationship Officer",
        "department": "Retail Banking",
        "location": "Accra Head Office",
        "manager": "Kofi Mensah",
        "grade": "B2",
        "employment_type": "permanent",
        "start_date": "2021-03-01",
    },
    "E1002": {
        "staff_number": "E1002",
        "name": "Yaw Boateng",
        "job_title": "Teller",
        "department": "Branch Operations",
        "location": "Accra Head Office",
        "manager": "Efua Addo",
        "grade": "A3",
        "employment_type": "fixed_term",
        "start_date": "2025-06-16",
    },
}


@dataclass
class _Ticket:
    request: HelpRequest
    staff_number: str
    description: str
    comments: list[Comment] = field(default_factory=list)


class DummyHr:
    """Implements HrRecordsClient, LeaveClient and HelpdeskClient."""

    def __init__(self, today: date | None = None) -> None:
        self.today = today or date.today()
        self.employees: dict[str, Employee] = {k: dict(v) for k, v in EMPLOYEES.items()}  # type: ignore[misc]
        self.taken: dict[str, dict[str, Decimal]] = {
            "E1001": {"annual": Decimal(8), "sick": Decimal(2)}
        }
        self.leave: list[tuple[str, LeaveRequest]] = []
        self.tickets: dict[str, _Ticket] = {}
        self.done: dict[str, Submitted] = {}  # request_id -> what it did: each request once
        self.counters = {"LV": 289, "HR": 420}
        self._seed()

    def _seed(self) -> None:
        year = self.today.year
        self.leave.append(
            (
                "E1001",
                {
                    "reference": f"LV-{year}-00288",
                    "leave_type": "annual",
                    "start": f"{year}-08-03",
                    "end": f"{year}-08-07",
                    "days": "5",
                    "status": "taken",
                    "approver": "Kofi Mensah",
                    "submitted": f"{year}-07-10",
                },
            )
        )
        self.tickets[f"HR-{year}-00419"] = _Ticket(
            {
                "reference": f"HR-{year}-00419",
                "category": "payroll",
                "subject": "Missing overtime payment for September",
                "status": "in_progress",
                "team": TEAMS["payroll"],
                "opened": f"{year}-10-02",
                "updated": f"{year}-10-06",
                "confidential": False,
            },
            "E1001",
            "My overtime for 12 and 19 September was not in my September pay.",
            [
                {
                    "by": "Payroll Support",
                    "at": f"{year}-10-06",
                    "text": "We have asked your branch to confirm the hours. "
                    "We will update you by 16 Oct.",
                },
            ],
        )

    # --- employee records ---------------------------------------------------------------------

    async def get_employee(self, staff_number: str) -> Employee:
        number = staff_number.strip().upper()
        if number not in self.employees:  # a dummy record for anyone who signs in
            self.employees[number] = {
                "staff_number": number,
                "name": f"Employee {number}",
                "job_title": "Officer",
                "department": "Operations",
                "location": "Accra Head Office",
                "manager": "Efua Addo",
                "grade": "B1",
                "employment_type": "permanent",
                "start_date": "2024-01-08",
            }
        return self.employees[number]

    # --- leave -----------------------------------------------------------------------------------

    async def leave_types(self) -> list[LeaveType]:
        return [dict(t) for t in LEAVE_TYPES]  # type: ignore[misc]

    async def holidays(self, location: str, year: int) -> list[Holiday]:
        return [dict(h) for h in HOLIDAYS.get(year, [])]  # type: ignore[misc]

    async def leave_requests(self, staff_number: str) -> list[LeaveRequest]:
        number = staff_number.strip().upper()
        return [dict(r) for owner, r in self.leave if owner == number]  # type: ignore[misc]

    async def balances(self, staff_number: str, year: int) -> list[LeaveBalance]:
        number = staff_number.strip().upper()
        await self.get_employee(number)
        booked: dict[str, Decimal] = {}
        for owner, r in self.leave:
            if (
                owner == number
                and r["status"] in ("waiting", "approved")
                and r["start"][:4] == str(year)
            ):
                booked[r["leave_type"]] = booked.get(r["leave_type"], Decimal(0)) + Decimal(
                    r["days"]
                )
        taken = self.taken.get(number, {})
        balances: list[LeaveBalance] = []
        for t in LEAVE_TYPES:
            if not t["counted"]:
                continue
            kind = t["leave_type"]
            entitled = Decimal(ENTITLED[kind])
            used, held = taken.get(kind, Decimal(0)), booked.get(kind, Decimal(0))
            balances.append(
                {
                    "leave_type": kind,
                    "title": t["title"],
                    "entitled": _days(entitled),
                    "taken": _days(used),
                    "booked": _days(held),
                    "remaining": _days(entitled - used - held),
                }
            )
        return balances

    async def submit(
        self, staff_number: str, leave_type: str, start: str, end: str, days: str, request_id: str
    ) -> Submitted:
        if request_id in self.done:
            return self.done[request_id]
        employee = await self.get_employee(staff_number)
        reference = self._next("LV")
        self.leave.append(
            (
                employee["staff_number"],
                {
                    "reference": reference,
                    "leave_type": leave_type,
                    "start": start,
                    "end": end,
                    "days": days,
                    "status": "waiting",
                    "approver": employee["manager"],
                    "submitted": self.today.isoformat(),
                },
            )
        )
        done: Submitted = {"reference": reference, "status": f"Waiting for {employee['manager']}"}
        self.done[request_id] = done
        return done

    # --- help desk -----------------------------------------------------------------------------

    async def help_requests(self, staff_number: str) -> list[HelpRequest]:
        number = staff_number.strip().upper()
        return [dict(t.request) for t in self.tickets.values() if t.staff_number == number]  # type: ignore[misc]

    def _ticket(self, staff_number: str, reference: str) -> _Ticket:
        ticket = self.tickets.get(reference.strip().upper())
        if ticket is None or ticket.staff_number != staff_number.strip().upper():
            raise NotFound(reference)  # another employee's request does not exist for them
        return ticket

    async def get_request(self, staff_number: str, reference: str) -> HelpRequest:
        return dict(self._ticket(staff_number, reference).request)  # type: ignore[return-value]

    async def comments(self, staff_number: str, reference: str) -> list[Comment]:
        return [dict(c) for c in self._ticket(staff_number, reference).comments]  # type: ignore[misc]

    async def create(
        self,
        staff_number: str,
        category: str,
        subject: str,
        description: str,
        request_id: str,
        confidential: bool = False,
    ) -> Submitted:
        if request_id in self.done:
            return self.done[request_id]
        number = staff_number.strip().upper()
        await self.get_employee(number)
        reference = self._next("HR")
        team = TEAMS.get(category, TEAMS["other"])
        today = self.today.isoformat()
        self.tickets[reference] = _Ticket(
            {
                "reference": reference,
                "category": category,
                "subject": subject,
                "status": "open",
                "team": team,
                "opened": today,
                "updated": today,
                "confidential": confidential,
            },
            number,
            description,
        )
        done: Submitted = {"reference": reference, "status": f"With {team}"}
        self.done[request_id] = done
        return done

    async def add_comment(
        self, staff_number: str, reference: str, text: str, request_id: str
    ) -> Submitted:
        if request_id in self.done:
            return self.done[request_id]
        ticket = self._ticket(staff_number, reference)
        ticket.comments.append({"by": "you", "at": self.today.isoformat(), "text": text})
        ticket.request["updated"] = self.today.isoformat()
        if ticket.request["status"] == "waiting_for_you":
            ticket.request["status"] = "in_progress"
        done: Submitted = {
            "reference": ticket.request["reference"],
            "status": f"Added to the request, with {ticket.request['team']}",
        }
        self.done[request_id] = done
        return done

    def _next(self, prefix: str) -> str:
        self.counters[prefix] += 1
        return f"{prefix}-{self.today.year}-{self.counters[prefix]:05d}"


def _days(value: Decimal) -> str:
    return format(value.normalize(), "f")
