"""Every write to proposed actions. A proposal changes only while it waits, under a row lock:
two clicks on Send claim it once. One found past its time is marked expired (and that is kept)
before the refusal is raised."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.actions.models import ProposedAction
from core.errors import ActionUnavailable

Status = ProposedAction.Status


def create(**values: Any) -> ProposedAction:
    return ProposedAction.objects.create(**values)


def claim(proposal_id: UUID, staff_id: str, now: datetime) -> ProposedAction:
    """Mark it being sent, if it is the caller's and still waits."""
    return _change(proposal_id, staff_id, now, Status.SENDING)


def cancel(proposal_id: UUID, staff_id: str, now: datetime) -> ProposedAction:
    return _change(proposal_id, staff_id, now, Status.CANCELLED)


def finish(
    proposal_id: UUID, status: str, reference: str = "", outcome: str = ""
) -> ProposedAction:
    found = ProposedAction.objects.get(id=proposal_id)
    found.status, found.reference, found.outcome = status, reference[:300], outcome[:300]
    found.decided_at = None if status == Status.PROPOSED else timezone.now()
    found.save(update_fields=["status", "reference", "outcome", "decided_at"])
    return found


def _change(proposal_id: UUID, staff_id: str, now: datetime, status: str) -> ProposedAction:
    with transaction.atomic():
        found = (
            ProposedAction.objects.select_for_update()
            .filter(id=proposal_id, staff_id=staff_id)
            .first()
        )
        if found is None:
            refused = "not_found"
        elif found.status == Status.PROPOSED and found.expires_at <= now:
            found.status = refused = Status.EXPIRED
            found.save(update_fields=["status"])
        elif found.status != Status.PROPOSED:
            refused = found.status
        else:
            refused = ""
            found.status = status
            found.decided_at = timezone.now() if status == Status.CANCELLED else None
            found.save(update_fields=["status", "decided_at"])
    if refused or found is None:
        raise ActionUnavailable(refused or "not_found")
    return found
