"""In-memory implementations of the core ports, for core tests without Django."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.types import Caller, Message, Playbook, PlaybookRunState


class InMemoryConversationStore:
    def __init__(self) -> None:
        self.owners: dict[UUID, str] = {}
        self.messages: dict[UUID, list[tuple[Message, str | None]]] = {}

    async def create(self, caller: Caller) -> UUID:
        conversation_id = uuid4()
        self.owners[conversation_id] = caller.id
        self.messages[conversation_id] = []
        return conversation_id

    async def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        history = [m for m, _ in self.messages.get(conversation_id, [])]
        return history[-limit:] if limit else []

    async def append(
        self, conversation_id: UUID, message: Message, feature_id: str | None = None
    ) -> None:
        self.messages.setdefault(conversation_id, []).append((message, feature_id))


class InMemoryPlaybookStore:
    def __init__(self, playbooks: list[Playbook] | None = None) -> None:
        self.playbooks = {p.id: p for p in playbooks or []}
        self.runs: dict[UUID, PlaybookRunState] = {}

    async def get(self, playbook_id: str) -> Playbook:
        return self.playbooks[playbook_id]

    async def list(self) -> list[Playbook]:
        return list(self.playbooks.values())

    async def get_run(self, conversation_id: UUID) -> PlaybookRunState | None:
        run = self.runs.get(conversation_id)
        return run if run and run.status == "active" else None

    async def save_run(self, conversation_id: UUID, state: PlaybookRunState) -> None:
        self.runs[conversation_id] = state


class InMemoryAudit:
    def __init__(self) -> None:
        self.events: list[tuple[Caller, str, dict[str, Any]]] = []

    async def record(self, caller: Caller, event: str, detail: dict[str, Any]) -> None:
        self.events.append((caller, event, detail))

    def names(self) -> list[str]:
        return [name for _, name, _ in self.events]


class FixedClock:
    def __init__(self, at: datetime | None = None) -> None:
        self.at = at or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.at
