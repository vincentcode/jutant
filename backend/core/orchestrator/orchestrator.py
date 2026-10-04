"""Orchestrator.ask(): the conversation loop."""

from collections.abc import AsyncIterator
from uuid import UUID

from core.events import Event
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.ports import AuditSink, ConversationStore, ModelProvider, PlaybookStore, ToolClient
from core.tools.gateway import ToolGateway
from core.types import Caller

NO_SOURCE_MESSAGE = "I could not find a source for that. Please check the relevant document."


class Orchestrator:
    def __init__(
        self,
        model: ModelProvider,
        tools: ToolClient,
        conversations: ConversationStore,
        playbooks: PlaybookStore,
        audit: AuditSink,
        registry: FeatureRegistry,
        router: FeatureRouter,
        gateway: ToolGateway,
        max_steps: int = 4,
        history_limit: int = 6,
    ):
        self.model = model
        self.tools = tools
        self.conversations = conversations
        self.playbooks = playbooks
        self.audit = audit
        self.registry = registry
        self.router = router
        self.gateway = gateway
        self.max_steps = max_steps
        self.history_limit = history_limit

    async def ask(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str | None = None,
    ) -> AsyncIterator[Event]:
        """Answer one question, streaming events.

        1. Audit `question_asked`; append the user message.
        2. Active playbook run -> hand to PlaybookRunner; stop.
        3. Resolve the feature (client choice or router); check role; emit FeatureSelected.
        4. Run the feature template (default: the tool loop, capped at `max_steps`).
        5. Collect citations; replace uncited answers where the template requires citations.
        6. Append the assistant message, audit `answer_returned`, emit Completed.
        """
        raise NotImplementedError
        yield  # pragma: no cover
