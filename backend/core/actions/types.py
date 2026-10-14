"""Confirmed actions: something done in a client system only once the person confirms it.

The model never does anything. A pack declares each action with two tools: `propose`, which the
model may call and which only checks the request and returns a draft, and `perform`, which no
feature lists and only `ActionService.confirm` calls, with the draft as it was shown.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

# proposed: shown, waiting; sending: confirmed, being done; sent: done (with its reference);
# failed: refused or broken for good; cancelled: by the person; expired: never confirmed in time.
ProposalStatus = Literal["proposed", "sending", "sent", "failed", "cancelled", "expired"]


@dataclass(frozen=True)
class Action:
    id: str  # "leave_request"
    title: str  # "Leave request", the card's heading
    propose: str  # the tool that checks a request and returns a draft: "leave.propose_request"
    perform: str  # the tool that does it: "leave.submit_request"; never given to the model
    roles: tuple[str, ...] = ()  # roles that may propose it; empty = all
    expires_s: int = 600  # how long a draft waits to be confirmed
    icon: str = "send"  # a Lucide icon name for the card
    pack: str = ""  # the pack that declares it: its tools see the caller's role there

    def allows(self, role: str) -> bool:
        return not self.roles or role in self.roles


@dataclass(frozen=True)
class Field:
    label: str  # "From"
    value: str  # "Mon 10 Nov 2026"


@dataclass(frozen=True)
class Draft:
    """What the propose tool returned, checked in code: what the card shows, and the arguments
    the perform tool will be called with, exactly."""

    summary: str  # "Annual leave, 10-14 Nov 2026"
    fields: tuple[Field, ...]
    submit: dict[str, Any]
    notes: tuple[str, ...] = ()  # "Balance after this: 9 of 21 days"
    warnings: tuple[str, ...] = ()  # "14 Nov is half a day at Head Office"


@dataclass(frozen=True)
class Proposal:
    id: UUID
    action_id: str
    title: str
    icon: str
    conversation_id: UUID
    caller_id: str  # only they may confirm or cancel it
    draft: Draft
    expires_at: datetime
    status: ProposalStatus = "proposed"
    reference: str = ""  # the request's number in the client system, once sent
    outcome: str = ""  # its status there ("Waiting for your manager"), or why it failed
    created_at: datetime | None = None
