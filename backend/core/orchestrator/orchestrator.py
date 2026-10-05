"""Orchestrator.ask(): one question in, a stream of events out.

1. Audit the question.
2. If a playbook is in progress in this conversation, the reply goes to the playbook runner,
   unless staff picked a different feature, which ends the playbook.
3. Otherwise resolve the feature: the one staff picked, or the router's choice. Check the caller's
   role may use it.
4. Run the feature's template (for most features, the tool loop).
5. Collect citations from the tool results. A template that requires citations never returns an
   uncited answer: it is replaced with a fixed "no source found" message. Such answers are held
   back until this check is done, rather than streamed as they arrive.
6. Store the answer, audit it with where the time went (routing, model, tools), and finish
   with Completed (or Failed).
"""

import time
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
    ToolFinished,
    ToolStarted,
)
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.features.templates import TEMPLATES, FeatureContext, FeatureTemplate
from core.orchestrator.citations import collect
from core.orchestrator.context import build_messages
from core.orchestrator.timing import TimedModel, TurnTimer
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
        timer = TurnTimer()
        await self.audit.record(
            caller,
            "question_asked",
            {"conversation_id": str(conversation_id), "text": text, "feature_id": feature_id},
        )
        run = await self.playbooks.get_run(conversation_id)
        if run is not None and feature_id and feature_id != run.feature_id:
            await self.runner.abandon(caller, conversation_id)  # staff moved on to something else
            run = None
        if run is not None:
            await self.conversations.append(conversation_id, Message("user", text))
            events = self.runner.advance(caller, conversation_id, text)
            async for event in self._finish(
                caller, conversation_id, run.feature_id, events, timer=timer
            ):
                yield event
            return

        feature = await self._resolve(caller, conversation_id, text, feature_id)
        timer.route_s = time.perf_counter() - timer.started
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
            model=TimedModel(self.model, timer),
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
            caller,
            conversation_id,
            feature.id,
            events,
            template.requires_citation,
            ctx.results,
            timer,
        ):
            yield event

    async def _resolve(
        self, caller: Caller, conversation_id: UUID, text: str, feature_id: str | None
    ) -> Feature:
        detail: dict[str, object] = {"conversation_id": str(conversation_id)}
        if feature_id:
            try:
                feature = self.registry.get(feature_id)
            except KeyError:
                raise PolicyDenied(f"unknown feature {feature_id}") from None
            detail["chosen_by"] = "client"
        else:
            try:
                route = await self.router.route(caller, text)
            except LookupError:
                raise PolicyDenied(f"no features for role {caller.role}") from None
            feature = route.feature
            detail["chosen_by"] = route.by  # pattern, meaning, model... to find misroutes
            if route.score is not None:
                detail["score"] = route.score
        if not feature.allows(caller.role):
            raise PolicyDenied(f"role {caller.role} may not use {feature.id}")
        await self.audit.record(caller, "feature_routed", {**detail, "feature_id": feature.id})
        return feature

    async def _finish(
        self,
        caller: Caller,
        conversation_id: UUID,
        feature_id: str,
        events: AsyncIterator[Event],
        requires_citation: bool = False,
        results: list[ToolResult] | None = None,
        timer: TurnTimer | None = None,
    ) -> AsyncIterator[Event]:
        """Pass the template's events on, then check citations, store and audit the answer.

        Text that needs citations streams only once the turn has some: until then it is held
        back, since it may yet be replaced. Citations only accumulate, so text sent once the
        turn has them can never be replaced.
        """
        timer = timer or TurnTimer()
        tool_started = 0.0
        text = ""  # the answer so far, with paragraph breaks
        sent = 0  # how much of it has been passed on
        steps: list[str] = []
        calls: list[ToolCall] = []
        try:
            async for event in events:
                if isinstance(event, Failed):
                    await self._audit_answer(
                        caller, conversation_id, feature_id, timer, failed=event.reason
                    )
                    yield event
                    return
                if isinstance(event, TextDelta):
                    if not event.text:
                        continue
                    text += event.text if event.continues or not text else f"\n\n{event.text}"
                    if requires_citation and not collect(results or []):
                        continue  # held back: it may be replaced by NO_SOURCE_MESSAGE
                    yield TextDelta(text[sent:], continues=sent > 0)
                    sent = len(text)
                    continue
                if isinstance(event, ToolStarted):
                    calls.append(event.call)
                    tool_started = time.perf_counter()
                elif isinstance(event, ToolFinished):
                    timer.tool_s += time.perf_counter() - tool_started
                elif isinstance(event, PlaybookStepShown):
                    steps.append(
                        f"Step {event.step.order}: {event.step.title}. {event.step.instruction}"
                    )
                yield event
        except ModelUnavailable:
            await self._audit_answer(
                caller, conversation_id, feature_id, timer, failed=MODEL_UNAVAILABLE
            )
            yield Failed(MODEL_UNAVAILABLE)
            return

        citations = collect(results or [])
        if requires_citation and not citations:
            text, sent = NO_SOURCE_MESSAGE, 0  # nothing was sent: no citations, no streaming
        if len(text) > sent:
            yield TextDelta(text[sent:], continues=sent > 0)

        # History keeps the playbook steps too, so later turns have the context they need.
        stored = "\n\n".join(p for p in (text, *steps) if p)
        await self.conversations.append(
            conversation_id, Message("assistant", stored), feature_id or None, citations
        )
        await self._audit_answer(
            caller,
            conversation_id,
            feature_id,
            timer,
            citations=len(citations),
            tools=[c.name for c in calls],
        )
        yield Completed(Answer(text, feature_id, citations, tuple(calls)))

    async def _audit_answer(
        self,
        caller: Caller,
        conversation_id: UUID,
        feature_id: str,
        timer: TurnTimer,
        **detail: object,
    ) -> None:
        await self.audit.record(
            caller,
            "answer_returned",
            {
                "conversation_id": str(conversation_id),
                "feature_id": feature_id,
                **detail,
                "timing": timer.as_detail(),  # where the turn's time went
            },
        )
