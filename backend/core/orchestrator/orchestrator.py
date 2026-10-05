"""Orchestrator.ask(): one question in, a stream of events out.

1. Audit the question.
2. If a playbook is in progress in this conversation, the reply goes to the playbook runner.
3. Otherwise resolve the feature: the one staff picked, or the router's choice. Check the caller's
   role may use it.
4. Run the feature's template (for most features, the tool loop).
5. Collect citations from the tool results. A template that requires citations never returns an
   uncited answer: it is replaced with a fixed "no source found" message. Such answers are held
   back until this check is done, rather than streamed as they arrive.
6. Store the answer, audit it, and finish with Completed (or Failed).
"""

from collections.abc import AsyncIterator, Mapping
from uuid import UUID

from core.errors import ModelUnavailable, PolicyDenied
from core.events import (
    Completed,
    Event,
    Failed,
    FeatureSelected,
    PlaybookStepShown,
    TextDelta,
    ToolStarted,
)
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.features.templates import TEMPLATES, FeatureContext, FeatureTemplate
from core.orchestrator.citations import collect
from core.orchestrator.context import build_messages
from core.playbooks.runner import PlaybookRunner
from core.ports import AuditSink, ConversationStore, ModelProvider, PlaybookStore, ToolClient
from core.tools.gateway import ToolGateway
from core.types import Answer, Caller, Feature, Message, ToolCall, ToolResult

NO_SOURCE_MESSAGE = (
    "I could not find a source for that, so I can't answer it reliably. "
    "Please check the relevant document or ask a colleague."
)
MODEL_UNAVAILABLE = "model_unavailable"


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
        system_prompt: str = "",
        extraction_schemas: Mapping[str, list[str]] | None = None,
        templates: Mapping[str, FeatureTemplate] = TEMPLATES,
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
        self.system_prompt = system_prompt
        self.extraction_schemas = dict(extraction_schemas or {})
        self.templates = templates
        self.runner = PlaybookRunner(playbooks, audit, model)

    async def load_tools(self) -> None:
        """Read the tool list from every MCP server. Call once at start-up."""
        await self.gateway.catalog.load()

    async def ask(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str | None = None,
        upload_text: str | None = None,
    ) -> AsyncIterator[Event]:
        """Answer one question, streaming events.

        Raises PolicyDenied before the first event if the caller may not use the feature.
        """
        await self.audit.record(
            caller,
            "question_asked",
            {"conversation_id": str(conversation_id), "text": text, "feature_id": feature_id},
        )
        run = await self.playbooks.get_run(conversation_id)
        if run is not None:
            await self.conversations.append(conversation_id, Message("user", text))
            events = self.runner.advance(caller, conversation_id, text)
            async for event in self._finish(caller, conversation_id, run.feature_id, events):
                yield event
            return

        feature = await self._resolve(caller, conversation_id, text, feature_id)
        history = await self.conversations.recent_messages(conversation_id, self.history_limit)
        await self.conversations.append(conversation_id, Message("user", text))
        yield FeatureSelected(feature.id)

        template = self.templates[feature.template]
        ctx = FeatureContext(
            caller=caller,
            conversation_id=conversation_id,
            feature=feature,
            question=text,
            messages=build_messages(self.system_prompt, feature, history, text),
            model=self.model,
            gateway=self.gateway,
            playbooks=self.playbooks,
            runner=self.runner,
            audit=self.audit,
            max_steps=self.max_steps,
            upload_text=upload_text,
            extraction_schemas=self.extraction_schemas,
        )
        events = template.run(ctx)
        async for event in self._finish(
            caller, conversation_id, feature.id, events, template.requires_citation, ctx.results
        ):
            yield event

    async def _resolve(
        self, caller: Caller, conversation_id: UUID, text: str, feature_id: str | None
    ) -> Feature:
        if feature_id:
            try:
                feature = self.registry.get(feature_id)
            except KeyError:
                raise PolicyDenied(f"unknown feature {feature_id}") from None
            chosen_by = "client"
        else:
            try:
                feature = await self.router.route(caller, text)
            except LookupError:
                raise PolicyDenied(f"no features for role {caller.role}") from None
            chosen_by = "router"
        if not feature.allows(caller.role):
            raise PolicyDenied(f"role {caller.role} may not use {feature.id}")
        await self.audit.record(
            caller,
            "feature_routed",
            {
                "conversation_id": str(conversation_id),
                "feature_id": feature.id,
                "chosen_by": chosen_by,
            },
        )
        return feature

    async def _finish(
        self,
        caller: Caller,
        conversation_id: UUID,
        feature_id: str,
        events: AsyncIterator[Event],
        requires_citation: bool = False,
        results: list[ToolResult] | None = None,
    ) -> AsyncIterator[Event]:
        """Pass the template's events on, then check citations, store and audit the answer."""
        texts: list[str] = []
        steps: list[str] = []
        calls: list[ToolCall] = []
        try:
            async for event in events:
                if isinstance(event, Failed):
                    await self._audit_answer(
                        caller, conversation_id, feature_id, failed=event.reason
                    )
                    yield event
                    return
                if isinstance(event, TextDelta):
                    texts.append(event.text)
                    if requires_citation:
                        continue  # held back until citations are checked
                elif isinstance(event, ToolStarted):
                    calls.append(event.call)
                elif isinstance(event, PlaybookStepShown):
                    steps.append(
                        f"Step {event.step.order}: {event.step.title}. {event.step.instruction}"
                    )
                yield event
        except ModelUnavailable:
            await self._audit_answer(caller, conversation_id, feature_id, failed=MODEL_UNAVAILABLE)
            yield Failed(MODEL_UNAVAILABLE)
            return

        citations = collect(results or [])
        text = "\n\n".join(t for t in texts if t)
        if requires_citation:
            if not citations:
                text = NO_SOURCE_MESSAGE
            yield TextDelta(text)

        # History keeps the playbook steps too, so later turns have the context they need.
        stored = "\n\n".join(p for p in (text, *steps) if p)
        await self.conversations.append(
            conversation_id, Message("assistant", stored), feature_id or None, citations
        )
        await self._audit_answer(
            caller,
            conversation_id,
            feature_id,
            citations=len(citations),
            tools=[c.name for c in calls],
        )
        yield Completed(Answer(text, feature_id, citations, tuple(calls)))

    async def _audit_answer(
        self, caller: Caller, conversation_id: UUID, feature_id: str, **detail: object
    ) -> None:
        await self.audit.record(
            caller,
            "answer_returned",
            {"conversation_id": str(conversation_id), "feature_id": feature_id, **detail},
        )
