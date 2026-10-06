"""The only write for audit: append an event, with personal data masked.

There is deliberately no update or delete: the audit log is append-only.
"""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.models import AuditEvent
from core.privacy.masking import mask


@transaction.atomic
def record_event(
    *,
    staff_id: str,
    role: str,
    event: str,
    detail: dict[str, Any],
    conversation_id: UUID | str | None = None,
    patterns: Mapping[str, str] | None = None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        staff_id=staff_id,
        role=role,
        event=event,
        detail=mask(detail, patterns),
        conversation_id=conversation_id or None,
    )
