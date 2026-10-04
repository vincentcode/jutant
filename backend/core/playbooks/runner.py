"""PlaybookRunner: step state machine.

The next step comes from `next_on` or the next order; the model never chooses it.
"cancel" or "stop" abandons the run.
"""

from collections.abc import AsyncIterator
from uuid import UUID

from core.events import Event
from core.ports import AuditSink, ModelProvider, PlaybookStore
from core.types import Caller

CANCEL_WORDS = frozenset({"cancel", "stop"})


class PlaybookRunner:
    def __init__(self, store: PlaybookStore, audit: AuditSink, model: ModelProvider | None = None):
        self.store = store
        self.audit = audit
        self.model = model  # only to rephrase a step or map free text onto a listed choice

    async def start(
        self, caller: Caller, conversation_id: UUID, playbook_id: str
    ) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def advance(
        self, caller: Caller, conversation_id: UUID, user_input: str
    ) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
