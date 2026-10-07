"""Every write for playbooks. Keyword-only arguments, atomic."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.playbooks.models import Playbook, PlaybookRun, Step
from core.types import Playbook as PlaybookDef


@transaction.atomic
def upsert_playbook(*, definition: PlaybookDef, replace: bool = False) -> tuple[Playbook, bool]:
    """Create a playbook from a pack definition. Returns the row and whether it was written.

    An existing playbook is left alone unless `replace` is set, because operations staff may
    have edited it in the admin since it was loaded. Replacing bumps its version.
    """
    playbook = Playbook.objects.select_for_update().filter(slug=definition.id).first()
    if playbook is not None and not replace:
        return playbook, False
    if playbook is None:
        playbook = Playbook(slug=definition.id)
    else:
        playbook.version += 1
        playbook.steps.all().delete()
    playbook.title = definition.title
    playbook.description = definition.description
    playbook.is_active = True
    playbook.save()
    Step.objects.bulk_create(
        Step(
            playbook=playbook,
            order=s.order,
            title=s.title,
            instruction=s.instruction,
            audience=list(s.audience),
            expects=s.expects,
            choices=list(s.choices),
            next_on=dict(s.next_on),
            lookup=asdict(s.lookup) if s.lookup else None,
            answer_from=s.answer_from or "",
        )
        for s in definition.steps
    )
    return playbook, True


@transaction.atomic
def save_run(
    *,
    conversation_id: UUID,
    playbook_id: str,
    current_order: int,
    answers: dict[int, str],
    status: str,
    feature_id: str = "",
    facts: dict[int, dict[str, Any]] | None = None,
    paused: bool = False,
) -> PlaybookRun:
    """Update the conversation's active run, or start a new one.

    A conversation has at most one active run; finished runs are kept for the record.
    """
    run = (
        PlaybookRun.objects.select_for_update()
        .filter(conversation_id=conversation_id, status=PlaybookRun.Status.ACTIVE)
        .first()
    ) or PlaybookRun(conversation_id=conversation_id)
    run.playbook_id = playbook_id
    run.current_order = current_order
    run.answers = {str(order): answer for order, answer in answers.items()}
    run.facts = {str(order): record for order, record in (facts or {}).items()}
    run.status = status
    run.feature_id = feature_id
    run.paused = paused
    run.save()
    return run
