"""Leave, worked out in code: the facts about an employee's leave, and whether a request can be
made, with what the card shows. Pure functions over the records the systems return.

The model never counts days or checks a balance: it would get them wrong, and an employee
would act on it. A request is checked here before it is shown (`propose`), and again before it
is sent, in case the balance changed meanwhile.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from packs.hr.adapters.base import (
    Employee,
    Holiday,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
)

OPEN = ("waiting", "approved")  # requests that still hold days
LONGEST = 90  # calendar days one request may cover; longer goes through HR


def day(iso: str) -> str:
    """ "2026-11-10" -> "Tue 10 Nov 2026" """
    d = date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b %Y}"


def span(start: str, end: str) -> str:
    """ "10-14 Nov 2026", "28 Dec 2026 - 3 Jan 2027", or one day."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a == b:
        return f"{a.day} {a:%b %Y}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}-{b.day} {a:%b %Y}"
    if a.year == b.year:
        return f"{a.day} {a:%b} - {b.day} {b:%b %Y}"
    return f"{a.day} {a:%b %Y} - {b.day} {b:%b %Y}"


def working_days(start: str, end: str, holidays: Sequence[Holiday]) -> tuple[int, list[Holiday]]:
    """The working days from `start` to `end`, both included (not weekends, not public holidays),
    and the public holidays on weekdays in between, which are not counted."""
    closed = {h["date"]: h for h in holidays}
    counted, skipped = 0, []
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    while current <= last:
        if current.weekday() < 5:
            if current.isoformat() in closed:
                skipped.append(closed[current.isoformat()])
            else:
                counted += 1
        current += timedelta(days=1)
    return counted, skipped


def balance_facts(
    year: int, balances: Sequence[LeaveBalance], requests: Sequence[LeaveRequest]
) -> dict[str, str]:
    """What the employee's leave stands at, one line per type, and the leave still to come."""
    facts = {"year": str(year)}
    for b in balances:
        facts[b["title"]] = (
            f"{b['remaining']} of {b['entitled']} days left "
            f"({b['taken']} taken, {b['booked']} booked)"
        )
    coming = [r for r in requests if r["status"] in OPEN]
    facts["leave requested or approved"] = (
        "; ".join(
            f"{r['reference']}: {_title(r['leave_type'])}, {span(r['start'], r['end'])}, "
            f"{r['days']} days, {_status(r)}"
            for r in coming
        )
        or "none"
    )
    return facts


@dataclass(frozen=True)
class Check:
    """A request checked: a draft for the card, or why it cannot be made."""

    draft: dict[str, Any] | None = None
    refused: str = ""


def check(
    *,
    today: date,
    employee: Employee,
    kind: LeaveType | None,
    balance: LeaveBalance | None,
    period: str,
    holidays: Sequence[Holiday],
    requests: Sequence[LeaveRequest],
) -> Check:
    """Whether `employee` can ask for leave of `kind` over `period` ("start/end"), and if so
    the card: what will be sent, the balance after it, and what to know."""
    if kind is None:
        return Check(refused="There is no such kind of leave. Ask which kinds there are.")
    try:
        start, end = period.split("/")
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return Check(refused="Which days? Say them like 10 to 14 November.")
    if last < first:
        return Check(refused="The last day is before the first. Which days?")
    if (last - first).days >= LONGEST:
        return Check(refused=f"Leave of more than {LONGEST} days is arranged with HR directly.")
    if first < today and not kind["past_dates"]:
        return Check(refused=f"{kind['title']} cannot be for days already gone.")
    days, skipped = working_days(start, end, holidays)
    if days == 0:
        return Check(refused=f"{span(start, end)} has no working days: nothing to take.")
    for r in requests:
        if r["status"] in OPEN and r["start"] <= end and start <= r["end"]:
            return Check(
                refused=f"You already have leave for {span(r['start'], r['end'])} "
                f"({r['reference']}, {_status(r)})."
            )
    notes, warnings = [], []
    if kind["counted"] and balance is not None:
        left = Decimal(balance["remaining"]) - days
        if left < 0:
            return Check(
                refused=f"That is {days} working days, and you have {balance['remaining']} "
                f"days of {kind['title'].lower()} left."
            )
        notes.append(f"Balance after this: {_days(left)} of {balance['entitled']} days")
    for h in skipped:
        warnings.append(f"{day(h['date'])} is a public holiday ({h['name']}): not counted")
    if (first - today).days < kind["notice_days"] and first >= today:
        warnings.append(
            f"Less than {kind['notice_days']} days' notice: your manager may decline it"
        )
    if kind["evidence"]:
        notes.append(f"You will need: {kind['evidence']}")
    return Check(
        draft={
            "summary": f"{kind['title']}, {span(start, end)}",
            "fields": [
                {"label": "Type", "value": kind["title"]},
                {"label": "From", "value": day(start)},
                {"label": "To", "value": day(end)},
                {"label": "Days", "value": f"{days} working day{'s' if days != 1 else ''}"},
                {"label": "Approver", "value": f"{employee['manager']} (your manager)"},
            ],
            "notes": notes,
            "warnings": warnings,
            "submit": {"leave_type": kind["leave_type"], "start": start, "end": end},
        }
    )


TITLES = {
    "annual": "Annual leave",
    "sick": "Sick leave",
    "compassionate": "Compassionate leave",
    "study": "Study leave",
    "maternity": "Maternity leave",
    "paternity": "Paternity leave",
    "unpaid": "Unpaid leave",
}


def _title(kind: str) -> str:
    return TITLES.get(kind, kind.replace("_", " ").capitalize())


def status_of(r: LeaveRequest) -> str:
    """Where a request stands, in the employee's words: "Waiting for Kofi Mensah"."""
    status = _status(r)
    return status[:1].upper() + status[1:]


def _status(r: LeaveRequest) -> str:
    if r["status"] == "waiting":
        return f"waiting for {r['approver']}"
    return r["status"]


def _days(value: Decimal) -> str:
    return format(value.normalize(), "f")
