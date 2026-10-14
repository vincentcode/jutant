"""DjangoActionStore: `core.ports.ActionStore` over the actions app. Rows become core
`Proposal`s here; nothing of the ORM crosses into core."""

from datetime import datetime
from uuid import UUID

from asgiref.sync import sync_to_async

from apps.actions import selectors, services
from apps.actions.models import ProposedAction
from core.actions.types import Draft, Field, Proposal, ProposalStatus


class DjangoActionStore:
    async def create(self, proposal: Proposal) -> None:
        draft = proposal.draft
        await sync_to_async(services.create)(
            id=proposal.id,
            conversation_id=proposal.conversation_id,
            staff_id=proposal.caller_id,
            action_id=proposal.action_id,
            title=proposal.title,
            icon=proposal.icon,
            summary=draft.summary,
            fields=[{"label": f.label, "value": f.value} for f in draft.fields],
            notes=list(draft.notes),
            warnings=list(draft.warnings),
            submit=draft.submit,
            expires_at=proposal.expires_at,
        )

    async def claim(self, proposal_id: UUID, caller_id: str, now: datetime) -> Proposal:
        return to_proposal(await sync_to_async(services.claim)(proposal_id, caller_id, now))

    async def finish(
        self, proposal_id: UUID, status: ProposalStatus, reference: str = "", outcome: str = ""
    ) -> Proposal:
        row = await sync_to_async(services.finish)(proposal_id, status, reference, outcome)
        return to_proposal(row)

    async def cancel(self, proposal_id: UUID, caller_id: str, now: datetime) -> Proposal:
        return to_proposal(await sync_to_async(services.cancel)(proposal_id, caller_id, now))

    async def for_conversation(self, conversation_id: UUID, caller_id: str) -> list[Proposal]:
        rows = await sync_to_async(selectors.for_conversation)(conversation_id, caller_id)
        return [to_proposal(r) for r in rows]


def to_proposal(row: ProposedAction) -> Proposal:
    return Proposal(
        id=row.id,
        action_id=row.action_id,
        title=row.title,
        icon=row.icon,
        conversation_id=row.conversation_id,
        caller_id=row.staff_id,
        draft=Draft(
            summary=row.summary,
            fields=tuple(Field(f["label"], f["value"]) for f in row.fields),
            submit=dict(row.submit),
            notes=tuple(row.notes),
            warnings=tuple(row.warnings),
        ),
        expires_at=row.expires_at,
        status=row.status,
        reference=row.reference,
        outcome=row.outcome,
        created_at=row.created_at,
    )
