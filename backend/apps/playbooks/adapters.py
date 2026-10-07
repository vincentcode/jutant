"""Implements core.ports.PlaybookStore on the playbook tables."""

from uuid import UUID

from asgiref.sync import sync_to_async

from apps.playbooks import selectors, services
from apps.playbooks.models import Playbook as PlaybookRow
from apps.playbooks.models import PlaybookRun
from core.types import Playbook, PlaybookRunState, PlaybookStep, StepLookup


class DjangoPlaybookStore:
    async def get(self, playbook_id: str) -> Playbook:
        """Raises KeyError for an unknown or inactive playbook."""
        row = await sync_to_async(selectors.get_playbook)(slug=playbook_id)
        if row is None:
            raise KeyError(playbook_id)
        return to_playbook(row)

    async def list(self) -> list[Playbook]:
        rows = await sync_to_async(selectors.list_playbooks)()
        return [to_playbook(row) for row in rows]

    async def get_run(self, conversation_id: UUID) -> PlaybookRunState | None:
        run = await sync_to_async(selectors.active_run)(conversation_id=conversation_id)
        return to_state(run) if run else None

    async def save_run(self, conversation_id: UUID, state: PlaybookRunState) -> None:
        await sync_to_async(services.save_run)(
            conversation_id=conversation_id,
            playbook_id=state.playbook_id,
            current_order=state.current_order,
            answers=state.answers,
            status=state.status,
            feature_id=state.feature_id,
            facts=state.facts,
            paused=state.paused,
        )


def to_playbook(row: PlaybookRow) -> Playbook:
    steps = sorted(row.steps.all(), key=lambda s: s.order)  # uses the prefetch
    return Playbook(
        id=row.slug,
        title=row.title,
        description=row.description,
        steps=tuple(
            PlaybookStep(
                order=s.order,
                title=s.title,
                instruction=s.instruction,
                audience=tuple(s.audience),
                expects=s.expects,
                choices=tuple(s.choices),
                next_on={str(k): int(v) for k, v in s.next_on.items()},
                lookup=StepLookup(**s.lookup) if s.lookup else None,
                answer_from=s.answer_from or None,
            )
            for s in steps
        ),
    )


def to_state(run: PlaybookRun) -> PlaybookRunState:
    return PlaybookRunState(
        playbook_id=run.playbook_id,
        current_order=run.current_order,
        answers={int(k): v for k, v in run.answers.items()},
        status=run.status,
        feature_id=run.feature_id,
        facts={int(k): v for k, v in (run.facts or {}).items()},
        paused=run.paused,
    )
