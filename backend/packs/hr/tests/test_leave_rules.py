"""Leave worked out in code: working days, and whether a request can be made."""

from datetime import date

from packs.hr.adapters.fake import EMPLOYEES, HOLIDAYS, LEAVE_TYPES
from packs.hr.domain.leave import check, span, working_days

TODAY = date(2026, 10, 13)  # a Tuesday
KINDS = {k["leave_type"]: k for k in LEAVE_TYPES}
ANNUAL = {
    "leave_type": "annual",
    "title": "Annual leave",
    "entitled": "21",
    "taken": "8",
    "booked": "0",
    "remaining": "13",
}


def checked(period: str, kind: str = "annual", balance=ANNUAL, requests=()):
    return check(
        today=TODAY,
        employee=EMPLOYEES["E1001"],
        kind=KINDS.get(kind),
        balance=balance,
        period=period,
        holidays=HOLIDAYS[2026] + HOLIDAYS[2027],
        requests=list(requests),
    )


def test_weekends_and_public_holidays_are_not_counted() -> None:
    assert working_days("2026-11-09", "2026-11-15", []) == (5, [])  # Mon to Sun
    days, skipped = working_days("2026-12-21", "2027-01-01", HOLIDAYS[2026] + HOLIDAYS[2027])
    assert days == 8  # 10 weekdays, less Christmas Day and New Year's Day (Boxing Day: Sat)
    assert [h["name"] for h in skipped] == ["Christmas Day", "New Year's Day"]


def test_a_request_shows_the_days_the_approver_and_the_balance_after() -> None:
    result = checked("2026-11-09/2026-11-13")
    assert result.refused == ""
    draft = result.draft
    assert draft["summary"] == "Annual leave, 9-13 Nov 2026"
    assert {f["label"]: f["value"] for f in draft["fields"]} == {
        "Type": "Annual leave",
        "From": "Mon 9 Nov 2026",
        "To": "Fri 13 Nov 2026",
        "Days": "5 working days",
        "Approver": "Kofi Mensah (your manager)",
    }
    assert draft["notes"] == ["Balance after this: 8 of 21 days"]
    assert draft["submit"] == {"leave_type": "annual", "start": "2026-11-09", "end": "2026-11-13"}


def test_a_holiday_inside_the_request_is_named_and_not_counted() -> None:
    draft = checked("2026-12-21/2026-12-31").draft
    assert "Fri 25 Dec 2026 is a public holiday (Christmas Day): not counted" in draft["warnings"]
    assert {f["label"]: f["value"] for f in draft["fields"]}["Days"] == "8 working days"


def test_requests_that_cannot_be_made_say_why() -> None:
    assert "13 days of annual leave left" in checked("2026-11-02/2026-11-27").refused
    assert "already gone" in checked("2026-10-05/2026-10-06").refused
    assert "no working days" in checked("2026-11-14/2026-11-15").refused  # a weekend
    booked = {
        "reference": "LV-2026-00290",
        "leave_type": "annual",
        "start": "2026-11-11",
        "end": "2026-11-12",
        "days": "2",
        "status": "waiting",
        "approver": "Kofi Mensah",
        "submitted": "2026-10-01",
    }
    assert "LV-2026-00290" in checked("2026-11-09/2026-11-13", requests=[booked]).refused
    assert "no such kind" in checked("2026-11-09/2026-11-13", kind="sabbatical").refused


def test_sick_leave_may_be_for_days_gone_and_says_what_is_needed() -> None:
    sick = {
        **ANNUAL,
        "leave_type": "sick",
        "title": "Sick leave",
        "entitled": "10",
        "taken": "2",
        "remaining": "8",
    }
    draft = checked("2026-10-05/2026-10-07", kind="sick", balance=sick).draft
    assert "You will need: A doctor's note for more than 2 days in a row" in draft["notes"]


def test_short_notice_is_a_warning_not_a_refusal() -> None:
    draft = checked("2026-10-14/2026-10-14").draft
    assert any("notice" in w for w in draft["warnings"])


def test_periods_read_as_staff_write_them() -> None:
    assert span("2026-12-28", "2027-01-03") == "28 Dec 2026 - 3 Jan 2027"
    assert span("2026-11-12", "2026-11-12") == "12 Nov 2026"
