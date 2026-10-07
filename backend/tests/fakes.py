"""In-memory implementations of the core ports, for core tests without Django."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from core.events import PlaybookStepShown
from core.playbooks.history import as_text
from core.types import Caller, Citation, Message, Playbook, PlaybookRunState


@dataclass(frozen=True)
class StoredMessage:
    message: Message
    feature_id: str | None
    citations: tuple[Citation, ...]
    steps: tuple[PlaybookStepShown, ...] = ()
    trace_context: dict[str, str] | None = None


class InMemoryConversationStore:
    def __init__(self) -> None:
        self.owners: dict[UUID, str] = {}
        self.messages: dict[UUID, list[StoredMessage]] = {}
        self.contexts: dict[UUID, dict[str, Any]] = {}

    async def create(self, caller: Caller) -> UUID:
        conversation_id = uuid4()
        self.owners[conversation_id] = caller.id
        self.messages[conversation_id] = []
        return conversation_id

    async def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        history = [
            replace(
                stored.message,
                content=as_text(stored.message.content, stored.steps),
                feature_id=stored.feature_id,
                citations=stored.citations,
            )
            for stored in self.messages.get(conversation_id, [])
        ]
        return history[-limit:] if limit else []

    async def append(
        self,
        conversation_id: UUID,
        message: Message,
        feature_id: str | None = None,
        citations: tuple[Citation, ...] = (),
        steps: tuple[PlaybookStepShown, ...] = (),
        trace_context: Mapping[str, str] | None = None,
    ) -> None:
        stored = StoredMessage(message, feature_id, citations, steps, dict(trace_context or {}))
        self.messages.setdefault(conversation_id, []).append(stored)

    async def context(self, conversation_id: UUID) -> dict[str, Any]:
        return dict(self.contexts.get(conversation_id, {}))

    async def save_context(self, conversation_id: UUID, context: dict[str, Any]) -> None:
        self.contexts[conversation_id] = dict(context)


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
