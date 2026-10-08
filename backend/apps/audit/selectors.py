"""Every read query for audit."""

from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from apps.audit.models import AuditEvent


def events_for_conversation(*, conversation_id: UUID) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(conversation_id=conversation_id).order_by("at"))


def events_for_staff(*, staff_id: str, limit: int = 100) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(staff_id=staff_id).order_by("-at")[:limit])


def events_since(
    *, since: datetime, names: Collection[str], excluding_staff: Collection[str] = ()
) -> list[AuditEvent]:
    """Every event of these kinds since `since`, oldest first, but those of `excluding_staff`."""
    events = AuditEvent.objects.filter(at__gte=since, event__in=names)
    return list(events.exclude(staff_id__in=excluding_staff).order_by("at"))
