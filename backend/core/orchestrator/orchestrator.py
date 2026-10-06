"""Orchestrator.ask(): one question in, a stream of events out.

1. Audit the question.
2. If a playbook is in progress in this conversation, the reply goes to the playbook runner,
   unless staff picked a different feature, which ends the playbook.
3. Otherwise resolve the feature: the one staff picked, or the router's choice. Staff's quick
   action is kept unless another feature is clearly closer; for a follow-up, the feature that
   answered last is kept unless the question clearly belongs elsewhere (see the router). Check
   the caller's role may use it.
4. Run the feature's template (for most features, the tool loop). A follow-up's lookups read
   the previous question too. If the question gives nothing the feature's lookups need (no
   reference, no customer number), the feature's `ask_for` question is the answer instead.
5. Collect citations from the tool results. A template that requires citations never returns an
   uncited answer: it is replaced with a fixed "no source found" message. Such answers are held
   back until this check is done, rather than streamed as they arrive.
6. Store the answer, audit it with where the time went (routing, model, tools), and finish
   with Completed (or Failed).

The turn is traced through the `Tracer` port, if one is given: a span for the turn, routing,
each model and tool call, and each playbook step shown.
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
from core.features.followup import is_follow_up, lookup_text, previous
from core.features.prefetch import planned_calls
from core.features.registry import FeatureRegistry
from core.features.router import FeatureRouter
from core.features.templates import TEMPLATES, FeatureContext, FeatureTemplate
from core.features.templates.base import call_tool
from core.observability import NOOP, Trace, TraceContent, TracedModel, Tracer
from core.orchestrator.citations import collect
from core.orchestrator.context import build_messages
from core.orchestrator.timing import TimedModel, TurnTimer
from core.playbooks.runner import Lookup, PlaybookRunner
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
        tracer: Tracer = NOOP,
        trace_content: TraceContent | None = None,
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
        self.tracer = tracer
        self.trace_content = trace_content or TraceContent()
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
        preferred_feature_id: str | None = None,
    ) -> AsyncIterator[Event]:
        """Answer one question, streaming events.

        `feature_id` is used whatever the question; `preferred_feature_id` only unless the
        question clearly belongs to another feature.
        Raises PolicyDenied before the first event if the caller may not use the feature.
        The whole turn is one trace: routing, model and tool calls, playbook steps.
        """
        root = Trace(self.tracer, self.trace_content)
        with root.span(
            "turn",
            "agent",
            session=str(conversation_id),
            user=caller.id,
            role=caller.role,
            input=root.text(text),
            feature=feature_id,
            preferred=preferred_feature_id,
        ) as turn:
            async for event in self._ask(
                caller, conversation_id, text, feature_id, upload_text, preferred_feature_id, turn
            ):
                yield event

    async def _ask(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str | None,
        upload_text: str | None,
        preferred_feature_id: str | None,
        turn: Trace,
    ) -> AsyncIterator[Event]:
        timer = TurnTimer()
        await self.audit.record(
            caller,
            "question_asked",
            {
                "conversation_id": str(conversation_id),
                "text": text,
                "feature_id": feature_id,
                "preferred_feature_id": preferred_feature_id,
            },
        )
        run = await self.playbooks.get_run(conversation_id)
        chosen = feature_id or preferred_feature_id
        if run is not None and chosen and chosen != run.feature_id:
            await self.runner.abandon(caller, conversation_id)  # staff moved on to something else
            run = None
        if run is not None:
            await self.conversations.append(conversation_id, Message("user", text))
            results: list[ToolResult] = []
            lookup = self._lookup(caller, conversation_id, run.feature_id, turn, results)
            events = self.runner.advance(caller, conversation_id, text, lookup)
            turn.set(feature=run.feature_id, playbook=run.playbook_id)
            async for event in self._finish(
                caller,
                conversation_id,
                run.feature_id,
                events,
                results=results,
                timer=timer,
                trace=turn,
            ):
                yield event
            return

        history = await self.conversations.recent_messages(conversation_id, self.history_limit)
        before = previous(history)
        continuing = self._continued(before.feature_id, text)
        feature = await self._resolve(
            caller, conversation_id, text, feature_id, turn, preferred_feature_id, continuing
        )
        timer.route_s = time.perf_counter() - timer.started
        await self.conversations.append(conversation_id, Message("user", text))
        switched = preferred_feature_id if preferred_feature_id not in (None, feature.id) else None
        yield FeatureSelected(feature.id, switched)

        lookup = lookup_text(text, before)
        if not upload_text and _lacks_details(feature, lookup):
            async for event in self._finish(
                caller, conversation_id, feature.id, _say(feature.ask_for), timer=timer, trace=turn
            ):
                yield event
            return

        template = self.templates[feature.template]
        ctx = FeatureContext(
            caller=caller,
            conversation_id=conversation_id,
            feature=feature,
            question=text,
            lookup_text=lookup,
            messages=build_messages(self.system_prompt, feature, history, text),
            model=TimedModel(TracedModel(self.model, turn), timer),
            gateway=self.gateway,
            playbooks=self.playbooks,
            runner=self.runner,
            audit=self.audit,
            max_steps=self.max_steps,
            upload_text=upload_text,
            extraction_schemas=self.extraction_schemas,
            trace=turn,
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
            turn,
        ):
            yield event

    def _lookup(
        self,
        caller: Caller,
        conversation_id: UUID,
        feature_id: str,
        trace: Trace,
        results: list[ToolResult],
    ) -> Lookup | None:
        """How a playbook step looks a record up: a tool call of the feature running the
        playbook, made as any other (feature check, policy, audit, trace)."""
        try:
            feature = self.registry.get(feature_id)
        except KeyError:
            return None

        async def lookup(call: ToolCall) -> ToolResult:
            result = await call_tool(
                self.gateway, trace, caller, feature, str(conversation_id), call
            )
            results.append(result)
            return result

        return lookup

    def _continued(self, feature_id: str | None, text: str) -> str | None:
        """For a follow-up, the feature that answered last, or the one its pack sends follow-ups
        to; none if its template does not carry on (a summary)."""
        if feature_id is None or not is_follow_up(text):
            return None
        try:
            feature = self.registry.get(feature_id)
        except KeyError:
            return None  # a feature the pack no longer has
        if feature.follow_ups:
            return feature.follow_ups
        template = self.templates.get(feature.template)
        return feature_id if getattr(template, "keeps_follow_ups", True) else None

    async def _resolve(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str | None,
        turn: Trace | None = None,
        prefer: str | None = None,
        continuing: str | None = None,
    ) -> Feature:
        turn = turn or Trace()
        detail: dict[str, object] = {"conversation_id": str(conversation_id)}
        if feature_id:
            try:
                feature = self.registry.get(feature_id)
            except KeyError:
                raise PolicyDenied(f"unknown feature {feature_id}") from None
            detail["chosen_by"] = "client"
        else:
            with turn.span("route", "chain") as routing:
                try:
                    route = await self.router.route(
                        caller, text, TracedModel(self.model, routing), prefer, continuing
                    )
                except LookupError:
                    raise PolicyDenied(f"no features for role {caller.role}") from None
                routing.set(
                    feature=route.feature.id,
                    routed_by=route.by,
                    score=route.score,
                    prefer=prefer,
                    continuing=continuing,
                )
            feature = route.feature
            detail["chosen_by"] = route.by  # pattern, meaning, model... to find misroutes
            if prefer:
                detail["preferred"] = prefer
            if continuing:
                detail["continuing"] = continuing
            if route.score is not None:
                detail["score"] = route.score
        if not feature.allows(caller.role):
            raise PolicyDenied(f"role {caller.role} may not use {feature.id}")
        await self.audit.record(caller, "feature_routed", {**detail, "feature_id": feature.id})
        turn.set(feature=feature.id, routed_by=detail["chosen_by"])
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
        trace: Trace | None = None,
    ) -> AsyncIterator[Event]:
        """Pass the template's events on, then check citations, store and audit the answer.

        Text that needs citations streams only once the turn has some: until then it is held
        back, since it may yet be replaced. Citations only accumulate, so text sent once the
        turn has them can never be replaced.
        """
        timer = timer or TurnTimer()
        trace = trace or Trace()
        tool_started = 0.0
        text = ""  # the answer so far, with paragraph breaks
        sent = 0  # how much of it has been passed on
        steps: list[PlaybookStepShown] = []
        calls: list[ToolCall] = []
        try:
            async for event in events:
                if isinstance(event, Failed):
                    trace.fail(event.reason)
                    trace.set(failed=event.reason, **_timing(timer))
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
                    with trace.span(
                        "playbook step",
                        "chain",
                        playbook=event.playbook_id,
                        step=event.step.order,
                        title=event.step.title,
                        expects=event.step.expects,
                    ):
                        pass
                    steps.append(event)
                yield event
        except ModelUnavailable:
            trace.fail(MODEL_UNAVAILABLE)
            trace.set(failed=MODEL_UNAVAILABLE, **_timing(timer))
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

        # The steps are kept with the answer, for the client to show and the model to read.
        await self.conversations.append(
            conversation_id,
            Message("assistant", text),
            feature_id or None,
            citations,
            tuple(steps),
            trace.carrier(),  # so feedback on this answer can find its trace
        )
        await self._audit_answer(
            caller,
            conversation_id,
            feature_id,
            timer,
            citations=len(citations),
            tools=[c.name for c in calls],
        )
        trace.set(output=trace.text(text), citations=len(citations), **_timing(timer))
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


def _lacks_details(feature: Feature, text: str) -> bool:
    """The feature asks for what its lookups need, and the question gives none of it."""
    return bool(feature.ask_for and feature.prefetch and not planned_calls(feature, text))


async def _say(text: str) -> AsyncIterator[Event]:
    yield TextDelta(text)


def _timing(timer: TurnTimer) -> dict[str, int]:
    return {f"timing.{name}": value for name, value in timer.as_detail().items()}
