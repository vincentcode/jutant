"""The only write for audit: append an event, masked."""

from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.models import AuditEvent


@transaction.atomic
def record_event(
    *,
    staff_id: str,
    role: str,
    event: str,
    detail: dict[str, Any],
    conversation_id: UUID | None = None,
) -> AuditEvent:
    raise NotImplementedError
