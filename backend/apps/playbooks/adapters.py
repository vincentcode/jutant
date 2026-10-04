"""Implements core.ports.PlaybookStore."""

from uuid import UUID

from core.types import Playbook, PlaybookRunState


class DjangoPlaybookStore:
    async def get(self, playbook_id: str) -> Playbook:
        raise NotImplementedError

    async def list(self) -> list[Playbook]:
        raise NotImplementedError

    async def get_run(self, conversation_id: UUID) -> PlaybookRunState | None:
        raise NotImplementedError

    async def save_run(self, conversation_id: UUID, state: PlaybookRunState) -> None:
        raise NotImplementedError
