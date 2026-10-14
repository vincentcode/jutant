"""HR help requests, in code: what an employee's requests stand at, and the cards for a new
request, a comment, and asking to talk to HR privately.

A confidential request is shown by its reference and status only: its subject and comments stay
with HR, and are never read out to the model.
"""

from collections.abc import Sequence
from typing import Any

from packs.hr.adapters.base import Comment, HelpRequest

CATEGORIES = {
    "payroll": "Pay and payslips",
    "leave": "Leave",
    "benefits": "Benefits",
    "documents": "Letters and documents",
    "policy": "A question about a policy",
    "other": "Something else",
}
TEAMS = {
    "payroll": "Payroll Support",
    "leave": "Leave Administration",
    "benefits": "Benefits",
    "documents": "HR Documents",
    "policy": "HR Advisory",
    "other": "HR Service Desk",
}
STATUS = {
    "open": "open",
    "in_progress": "being worked on",
    "waiting_for_you": "waiting for you",
    "resolved": "resolved",
    "closed": "closed",
}
SUBJECT_CHARS = 80
DETAILS_CHARS = 1000
MIN_WORDS = 4  # fewer says nothing HR can act on ("Payroll")
COMMENT_CHARS = 1000


def listing(leave: Sequence[str], requests: Sequence[HelpRequest]) -> dict[str, str]:
    """The employee's HR requests, one line each, newest first."""
    lines = [_line(r) for r in sorted(requests, key=lambda r: r["opened"], reverse=True)]
    return {
        "help requests": "; ".join(lines) or "none",
        "leave requests": "; ".join(leave) or "none",
    }


def details(request: HelpRequest, comments: Sequence[Comment]) -> dict[str, str]:
    """One request as facts. A confidential one: only that it exists and where it stands."""
    facts = {
        "reference": request["reference"],
        "status": STATUS.get(request["status"], request["status"]),
        "with": request["team"],
        "opened": request["opened"],
        "last updated": request["updated"],
    }
    if request["confidential"]:
        facts["confidential"] = "yes: its details are kept by HR and not shown here"
        return facts
    facts["subject"] = request["subject"]
    facts["category"] = CATEGORIES.get(request["category"], request["category"])
    if comments:
        latest = comments[-1]
        facts["latest update"] = f"{latest['at']}, {latest['by']}: {latest['text']}"
    return facts


def new_request(category: str, description: str) -> dict[str, Any]:
    """The card for a new help request, or a refusal saying what is missing."""
    text = " ".join(description.split())
    if category not in CATEGORIES:
        return {"refused": "Which kind of request is it?"}
    if len(text.split()) < MIN_WORDS:
        return {"refused": "Tell me in a sentence or two what the request is about."}
    subject = _subject(text)
    return {
        "summary": subject,
        "fields": [
            {"label": "Kind", "value": CATEGORIES[category]},
            {"label": "Subject", "value": subject},
            {"label": "Details", "value": text[:300] + ("…" if len(text) > 300 else "")},
            {"label": "Goes to", "value": TEAMS[category]},
        ],
        "notes": ["You can add to it later by giving its reference."],
        "submit": {"category": category, "subject": subject, "description": text[:DETAILS_CHARS]},
    }


def comment(request: HelpRequest, text: str) -> dict[str, Any]:
    text = " ".join(text.split())
    if not text:
        return {"refused": "What would you like to add?"}
    if request["status"] == "closed":
        return {"refused": f"{request['reference']} is closed. Make a new request instead."}
    return {
        "summary": f"Add to {request['reference']}",
        "fields": [
            {"label": "Request", "value": request["reference"]},
            {"label": "Adding", "value": text[:300] + ("…" if len(text) > 300 else "")},
            {"label": "Seen by", "value": request["team"]},
        ],
        "submit": {"reference": request["reference"], "comment": text[:COMMENT_CHARS]},
    }


CONTACT = {
    "private": "Talk privately about something sensitive",
    "general": "Talk to someone in HR",
}


def contact(kind: str) -> dict[str, Any]:
    """The card asking HR to get in touch. Nothing the employee wrote in the conversation is
    sent: only that they asked, and how."""
    if kind not in CONTACT:
        return {"refused": "Is it something sensitive, or a general question?"}
    private = kind == "private"
    return {
        "summary": CONTACT[kind],
        "fields": [
            {"label": "Who", "value": "Employee Relations" if private else "HR Service Desk"},
            {"label": "What happens", "value": "They will contact you within 1 working day"},
            {
                "label": "What is sent",
                "value": "Only that you asked to talk. Nothing you wrote here.",
            },
        ],
        "notes": ["Kept confidential: only HR sees it."] if private else [],
        "submit": {"kind": kind},
    }


def _line(r: HelpRequest) -> str:
    status = STATUS.get(r["status"], r["status"])
    if r["confidential"]:
        return f"{r['reference']}: confidential, {status}"
    return f"{r['reference']}: {r['subject']}, {status}, with {r['team']}"


def _subject(text: str) -> str:
    first = text.split(". ")[0].rstrip(".")
    return first if len(first) <= SUBJECT_CHARS else first[: SUBJECT_CHARS - 1].rstrip() + "…"
