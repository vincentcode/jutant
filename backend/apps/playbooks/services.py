"""Every write for playbooks. Keyword-only arguments, atomic."""

from typing import Any
from uuid import UUID

from django.db import transaction

from apps.playbooks.models import Playbook, PlaybookRun


@transaction.atomic
def upsert_playbook(*, definition: dict[str, Any]) -> Playbook:
    """Create or replace a playbook and its steps from a pack YAML definition."""
    raise NotImplementedError


@transaction.atomic
def save_run(
    *,
    conversation_id: UUID,
    playbook_id: str,
    current_order: int,
    answers: dict[int, str],
    status: str,
) -> PlaybookRun:
    raise NotImplementedError
