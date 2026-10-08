"""Orchestrator.ask(): one question in, a stream of events out.

1. Audit the question.
2. Read the turn against the conversation's context (`core.context`): a stack of subjects, each
   with its entities (TX-0002), its feature and, for a procedure, its run. The message continues
   a subject, returns to an earlier one, starts a new one, or stops the procedure. Certain cases
   need no model (a step answer clicked on its card, a locked feature, a message naming an
   entity); the rest is read by the model with the stack in view. If it cannot tell, staff
   are asked (`Clarify`): the open subjects, the waiting step and the kinds of help, to pick
   from; the message is sent again saying which, and nothing is kept until then.
3. A procedure's turn goes to the playbook runner: the step's answer, or its step shown again.
4. Otherwise answer with the subject's feature (for a new subject: the one staff locked, or the
   router's choice, given staff's quick action; in the `agent` turn mode, the conversation's:
   see below). Check the caller's role may use it. Run its
   template with the subject's entities, so lookups use them ("why did it fail?" after TX-0002),
   and its own last few exchanges as history. If the subject lacks what the feature's lookups
   need, the feature's `ask_for` question is the answer instead. A procedure below the top waits
   (paused) until staff return to it.
5. Collect citations from the tool results. A template that requires citations never returns an
   uncited answer: it is replaced with a fixed "no source found" message. Such answers are held
   back until this check is done, rather than streamed as they arrive.
6. Store the answer, keep what the turn looked at in its subject, audit it with where the time
   went (routing, model, tools), and finish with Completed (or Failed).

Turn modes. In `route` mode a new subject's feature is the router's choice, and the pack's
conversation feature (a template that is not a subject, `keeps_subject = False`) is where it
sends what fits nothing. In `hybrid` mode the router decides only when it is sure (a pattern, a
clear meaning); anything less goes to the conversation, which decides or asks. In `agent`
mode the conversation feature takes every new subject staff did not lock. The conversation sees
the role's features as tools and calls one (`HandOver`: the message is answered with that
feature, as if routed there), asks staff to pick from a few (`Clarify`), or talks; it is told
what the assistant can and cannot do for the caller (`core.features.catalogue`).

The turn is traced through the `Tracer` port, if one is given: a span for the turn, reading it,
routing, each model and tool call, and each playbook step shown.
"""

import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from typing import Literal
from uuid import UUID

from core.context import (
    DOCUMENT,
    ContextStack,
    Frame,
    entities_in,
    from_calls,
    names_in,
    values_in,
)
from core.context.reader import Reading, ReplyAs, certain, read, same_subject
from core.errors import ModelUnavailable, PolicyDenied
from core.events import (
    Choice,
    Clarify,
    ClarifyReason,
    Completed,
    Event,
    Failed,
    FeatureSelected,
    HandOver,
    PlaybookStepShown,
    TextDelta,
    ToolFinished,
    ToolStarted,
)
from core.features.catalogue import catalogue
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
from core.types import (
    Answer,
    Caller,
    EntityType,
    Feature,
    Message,
    ToolCall,
    ToolResult,
)

NO_SOURCE_MESSAGE = (
    "I could not find a source for that, so I can't answer it reliably. "
    "Please check the relevant document or ask a colleague."
)
MODEL_UNAVAILABLE = "model_unavailable"
WHICH = "I'm not sure what this is about. Which is it?"
START = "What would you like to know?"
EXAMPLE = " For example: “{example}”"
PROCEDURE_TEMPLATE = "guided_playbook"
TurnMode = Literal["route", "hybrid", "agent"]


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
        entity_types: Sequence[EntityType] = (),
        turn_mode: TurnMode = "route",
        tool_labels: Mapping[str, str] | None = None,
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
        self.entity_types = tuple(entity_types)  # the pack's: what staff talk about
        self.runner = PlaybookRunner(playbooks, audit, model)
        self.turn_mode = turn_mode
        self.tool_labels = dict(tool_labels or {})  # what each tool looks at, in staff's words

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
        reply_as: ReplyAs | None = None,
        subject_id: int | None = None,
        picked: int | None = None,
    ) -> AsyncIterator[Event]:
        """Answer one question, streaming events.

        `feature_id` is used whatever the question; `preferred_feature_id` only unless the
        question clearly belongs to another feature. `reply_as`: what staff say the message is,
        during a procedure (a step answer clicked on its card, resume, stop...), or a subject
        chip clicked (`return`, with its `subject_id`). `picked`: the message is sent again
        after staff picked this choice (its position) in a `Clarify`; recorded, to measure asking.
        Raises PolicyDenied before the first event if the caller may not use the feature.
        The whole turn is one trace: reading it, routing, model and tool calls, playbook steps.
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
                caller,
                conversation_id,
                text,
                feature_id,
                upload_text,
                preferred_feature_id,
                reply_as,
                subject_id,
                turn,
                picked,
            ):
                yield event

    async def subjects(self, conversation_id: UUID) -> list[tuple[int, str, bool]]:
        """The conversation's open subjects, top first: (id, title, is a procedure)."""
        stack = ContextStack.from_dict(await self.conversations.context(conversation_id))
        current = await self.runner.current(conversation_id)
        return [(f.id, self._describe(f, current, stack), f.procedure) for f in stack.frames]

    async def _ask(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str | None,
        upload_text: str | None,
        preferred_feature_id: str | None,
        reply_as: ReplyAs | None,
        subject_id: int | None,
        turn: Trace,
        picked: int | None = None,
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
                "reply_as": reply_as,
                "picked": picked,
            },
        )
        # A pick sends the message again: it is stored once, when first asked.
        stored = picked is not None and await self._last_question(conversation_id) == text
        stack = ContextStack.from_dict(await self.conversations.context(conversation_id))
        stack.turn += 1
        if reply_as == "start" and feature_id:
            async for event in self._start(caller, conversation_id, text, feature_id, stack, timer):
                yield event
            return
        mentioned = entities_in(text, self.entity_types, stack.names)
        top = stack.top
        waiting = await self.runner.current(conversation_id) if top and top.procedure else None
        step = waiting[1] if waiting else None
        reading = certain(stack, text, mentioned, reply_as, feature_id, subject_id, step)
        if reading is None:
            reading = await self._read(caller, conversation_id, text, stack, turn, timer)
            if reading is not None and not mentioned:
                same_kind = self._same_kind(stack, reading)
                if same_kind is not None and self._only_it(same_kind, text):
                    reading = Reading("continue", same_kind.id, by="needs")
                elif same_kind is not None:
                    reading = await self._which_subject(
                        text, stack, same_kind, reading, turn, timer
                    )
                    if reading is None:  # neither the model nor the rules can tell: ask staff
                        feature = self._feature(same_kind.feature_id)
                        choices = (
                            Choice(
                                "subject",
                                self._describe(same_kind, None, stack),
                                subject_id=same_kind.id,
                                feature_id=same_kind.feature_id,
                            ),
                            Choice("feature", f"Another: {feature.title}", feature_id=feature.id),
                        )
                        async for event in self._clarify(
                            caller,
                            conversation_id,
                            text,
                            choices,
                            same_kind.feature_id,
                            "same_or_new",
                            stored,
                        ):
                            yield event
                        return
        if reading is None:  # the model could not tell: staff say what it is
            choices = await self._choices(caller, conversation_id, stack)
            async for event in self._clarify(
                caller,
                conversation_id,
                text,
                choices,
                stack.top.feature_id if stack.top else "",
                "unread",
                stored,
            ):
                yield event
            return
        turn.set(context=reading.action, read_by=reading.by)
        await self.audit.record(
            caller,
            "turn_read",
            {
                "conversation_id": str(conversation_id),
                "action": reading.action,
                "frame": reading.frame_id,
                "feature_id": reading.feature_id,
                "by": reading.by,
            },
        )

        frame = stack.get(reading.frame_id) if reading.frame_id is not None else None
        if frame is not None and not frame.procedure and reply_as == "return":
            async for event in self._back_to(
                caller, conversation_id, text, stack, frame, timer, stored
            ):
                yield event
            return
        if (
            frame is not None
            and frame.procedure
            and reading.action in ("continue", "return", "stop")
        ):
            async for event in self._procedure_turn(
                caller, conversation_id, text, stack, frame, reading, turn, timer, stored
            ):
                yield event
            return

        step_context = await self._waiting_step(conversation_id, stack)
        switched = None
        if frame is not None:  # continue or return to a subject
            frame = stack.bring_to_top(frame.id).with_entities(mentioned)
            feature = self._feature(frame.feature_id)
            if feature.follow_ups and feature.follow_ups != feature.id:
                feature = self._feature(feature.follow_ups)  # a summary's follow-ups: Q&A
                frame = replace(frame, feature_id=feature.id, procedure=False, touched=stack.turn)
            stack.put(frame)
            await self._audit_route(caller, conversation_id, feature, reading.by, turn)
        else:  # a new subject
            open_procedure = stack.procedure_frame()
            feature = await self._resolve(
                caller,
                conversation_id,
                text,
                reading.feature_id,
                turn,
                preferred_feature_id,
                chosen_by=reading.by if reading.feature_id and not feature_id else None,
                # One procedure at a time: another starts only when staff lock it.
                exclude=self._procedure_features() if open_procedure and not feature_id else (),
            )
            starts_procedure = feature.template == PROCEDURE_TEMPLATE
            if starts_procedure and (open_procedure := stack.procedure_frame()) is not None:
                async for event in self._stop_quietly(
                    caller, conversation_id, stack, open_procedure
                ):
                    yield event
                step_context = ""
            inherited = {} if starts_procedure else self._case(stack, open_procedure, feature)
            frame = stack.push(feature.id, {**inherited, **mentioned}, procedure=starts_procedure)
            if preferred_feature_id not in (None, feature.id):
                switched = preferred_feature_id
        timer.route_s = time.perf_counter() - timer.started
        if (procedure := stack.procedure_frame()) is not None and procedure.id != frame.id:
            await self.runner.pause(conversation_id)  # it waits below this subject

        async for event in self._answer(
            caller,
            conversation_id,
            text,
            feature,
            frame,
            stack,
            upload_text=upload_text,
            switched=switched,
            step_context=step_context,
            turn=turn,
            timer=timer,
            handed=stored,
        ):
            yield event

    async def _last_question(self, conversation_id: UUID) -> str | None:
        """The last message staff sent in the conversation, if any."""
        for message in reversed(await self.conversations.recent_messages(conversation_id, 4)):
            if message.role == "user":
                return message.content
        return None

    async def _read(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        stack: ContextStack,
        turn: Trace,
        timer: TurnTimer,
    ) -> Reading | None:
        """The model's reading of the turn, with the stack in view."""
        top = stack.top
        assert top is not None
        current = await self.runner.current(conversation_id) if top.procedure else None
        step = current[1] if current else None
        descriptions = {f.id: self._describe(f, current, stack) for f in stack.frames}
        # In agent mode a new subject's feature is the conversation's to choose: the reading
        # only says it is new. (In hybrid mode the reading still names one, from the context.)
        new_only = self._agent() is not None
        features = [] if new_only else self.registry.for_role(caller.role)
        if stack.procedure_frame() is not None:  # one procedure at a time
            features = [f for f in features if f.template != PROCEDURE_TEMPLATE]
        with turn.span("read turn", "chain") as span:
            reading = await read(
                TimedModel(TracedModel(self.model, span), timer),
                text,
                stack,
                lambda f: descriptions[f.id],
                features,
                step,
            )
            span.set(
                action=reading.action if reading else "unclear",
                frame=reading.frame_id if reading else None,
                feature=reading.feature_id if reading else None,
            )
        return reading

    async def _choices(
        self, caller: Caller, conversation_id: UUID, stack: ContextStack
    ) -> tuple[Choice, ...]:
        """Everything an unread message might be: the reply to the waiting step, an open
        subject, the paused procedure, a kind of help, or something else."""
        choices: list[Choice] = []
        current = await self.runner.current(conversation_id)
        procedure = stack.procedure_frame()
        if procedure is not None and current is not None:
            title, step = current
            if stack.top is procedure:
                choices.append(
                    Choice(
                        "answer",
                        f"My answer to step {step.order}: {step.title}",
                        feature_id=procedure.feature_id,
                    )
                )
            else:
                choices.append(
                    Choice(
                        "resume", f"Back to the {title} procedure", feature_id=procedure.feature_id
                    )
                )
        choices += [
            Choice(
                "subject", self._describe(f, None, stack), subject_id=f.id, feature_id=f.feature_id
            )
            for f in stack.frames[:4]
            if not f.procedure
        ]
        choices += [
            Choice("feature", f.title, feature_id=f.id)
            for f in self.registry.for_role(caller.role)
            if not _passing(self.templates.get(f.template))
            and not (procedure is not None and f.template == PROCEDURE_TEMPLATE)
        ]
        choices.append(Choice("new", "Something else"))
        return tuple(choices)

    async def _clarify(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        choices: tuple[Choice, ...],
        feature_id: str,
        reason: ClarifyReason,
        stored: bool = False,
    ) -> AsyncIterator[Event]:
        """Ask staff what the message is. The message and the question are stored, so the
        conversation shows them; nothing is kept in its subjects: the message is sent again
        with staff's pick, and not stored twice."""
        asked = Clarify(WHICH, choices, reason)
        await self._audit_clarify(caller, conversation_id, asked)
        if not stored:
            await self.conversations.append(conversation_id, Message("user", text))
        await self.conversations.append(conversation_id, Message("assistant", WHICH), feature_id)
        yield TextDelta(WHICH)
        yield asked
        yield Completed(Answer(WHICH, feature_id, (), ()))

    async def _audit_clarify(self, caller: Caller, conversation_id: UUID, asked: Clarify) -> None:
        """What staff were asked to pick from, and why: `report_turns` reads it."""
        await self.audit.record(
            caller,
            "clarify_shown",
            {
                "conversation_id": str(conversation_id),
                "reason": asked.reason,
                "choices": [
                    {"kind": c.kind, "feature_id": c.feature_id, "subject_id": c.subject_id}
                    for c in asked.choices
                ],
            },
        )

    async def _procedure_turn(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        stack: ContextStack,
        frame: Frame,
        reading: Reading,
        turn: Trace,
        timer: TurnTimer,
        stored: bool = False,
    ) -> AsyncIterator[Event]:
        """The procedure's turn: stop it, show its step again, or take the step's answer.
        `stored`: the message is already stored (sent again after a pick)."""
        results: list[ToolResult] = []
        if reading.action == "stop":
            events = self.runner.stop(caller, conversation_id)
            stack.drop(frame.id)
        else:
            stack.bring_to_top(frame.id)
            if reading.action == "return":
                events = self.runner.resume(conversation_id)
            else:
                lookup = self._lookup(caller, conversation_id, frame.feature_id, turn, results)
                events = self.runner.advance(caller, conversation_id, text, lookup, reading.choice)
        if not stored:
            await self.conversations.append(conversation_id, Message("user", text))
        turn.set(feature=frame.feature_id)
        answer = None
        async for event in self._finish(
            caller,
            conversation_id,
            frame.feature_id,
            events,
            results=results,
            timer=timer,
            trace=turn,
        ):
            if isinstance(event, Completed):
                answer = event.answer
            yield event
        if await self.playbooks.get_run(conversation_id) is None:
            stack.drop(frame.id)  # finished or stopped
        elif answer is not None and (kept := stack.get(frame.id)) is not None:
            looked_at = from_calls(answer.tool_calls, answer.citations, self.entity_types)
            stack.put(
                kept.with_entities(looked_at)
                .with_related(_pointed_to(results, self.entity_types))
                .with_exchange(text, answer.text)
            )
        await self.conversations.save_context(conversation_id, stack.as_dict())

    async def _answer(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature: Feature,
        frame: Frame,
        stack: ContextStack,
        *,
        upload_text: str | None,
        switched: str | None,
        step_context: str,
        turn: Trace,
        timer: TurnTimer,
        handed: bool = False,
    ) -> AsyncIterator[Event]:
        """Answer the question with the subject's feature, then keep what it looked at.
        `handed`: the question is already stored (the conversation passed the turn to this
        feature, or the message was sent again after a pick)."""
        if not handed:
            await self.conversations.append(conversation_id, Message("user", text))

        search = "\n".join(
            part for part in (text, frame.entities.get(DOCUMENT, ""), step_context) if part
        )
        entities = {k: v for k, v in frame.entities.items() if k != DOCUMENT}
        answer: Answer | None = None
        if not upload_text and _lacks_details(feature, text, entities):
            events: AsyncIterator[Event] = _say(feature.ask_for)
            requires_citation, results = False, []
        else:
            template = self.templates[feature.template]
            open_procedure = stack.procedure_frame() is not None
            history = [
                message
                for question, reply in frame.exchanges
                for message in (Message("user", question), Message("assistant", reply))
            ]
            ctx = FeatureContext(
                caller=caller,
                conversation_id=conversation_id,
                feature=feature,
                question=text,
                search_text=search,
                entities=entities,
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
                entity_types=self.entity_types,
                offers=tuple(
                    (f.id, f.title, f.description)
                    for f in self.registry.for_role(caller.role)
                    if not _passing(self.templates.get(f.template))
                    # one procedure at a time: another is not offered while one is open
                    and not (open_procedure and f.template == PROCEDURE_TEMPLATE)
                ),
                prefer=switched,
                catalogue=catalogue(
                    self.registry, caller.role, self.tool_labels, _passing_ids(self)
                )
                if _passing(template)
                else "",
            )
            events = template.run(ctx)
            requires_citation, results = template.requires_citation, ctx.results
            if _passing(template):  # it may pass the turn on before saying anything
                first = await anext(events, None)
                if isinstance(first, HandOver):
                    async for event in self._hand_over(
                        caller,
                        conversation_id,
                        text,
                        first.feature_id,
                        frame,
                        stack,
                        switched=switched,
                        step_context=step_context,
                        turn=turn,
                        timer=timer,
                    ):
                        yield event
                    return
                events = _then(_once(first), events)
                switched = None  # talking is not answering for another feature
        yield FeatureSelected(feature.id, switched)
        async for event in self._finish(
            caller,
            conversation_id,
            feature.id,
            events,
            requires_citation,
            results,
            timer,
            turn,
        ):
            if isinstance(event, Completed):
                answer = event.answer
            yield event

        for result in results:
            if result.ok:
                stack.learn(names_in(result.data, self.entity_types))
        kept = stack.get(frame.id) or frame
        if answer is not None:
            found = from_calls(answer.tool_calls, answer.citations, self.entity_types)
            kept = (
                kept.with_entities(found)
                .with_related(_pointed_to(results, self.entity_types))
                .with_exchange(text, answer.text)
            )
        if feature.template == PROCEDURE_TEMPLATE and await self.playbooks.get_run(conversation_id):
            kept = replace(kept, procedure=True)
        if _passing(self.templates.get(feature.template)):
            # Small talk is not a subject: the one staff were on stays on top.
            stack.drop(kept.id)
            if (top := stack.top) is not None and top.procedure:
                await self.runner.unpause(conversation_id)
        else:
            stack.put(kept)
        await self.conversations.save_context(conversation_id, stack.as_dict())

    async def _hand_over(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str,
        frame: Frame,
        stack: ContextStack,
        *,
        switched: str | None,
        step_context: str,
        turn: Trace,
        timer: TurnTimer,
    ) -> AsyncIterator[Event]:
        """The conversation chose a feature for the message: it becomes a new subject with that
        feature, taking what the conversation's frame held (the entities the message named), and
        is answered as if routed there."""
        stack.drop(frame.id)
        feature = await self._resolve(
            caller, conversation_id, text, feature_id, turn, routed_by="model:hand_over"
        )
        starts_procedure = feature.template == PROCEDURE_TEMPLATE
        inherited = {} if starts_procedure else self._case(stack, stack.procedure_frame(), feature)
        new = stack.push(feature.id, {**inherited, **frame.entities}, procedure=starts_procedure)
        async for event in self._answer(
            caller,
            conversation_id,
            text,
            feature,
            new,
            stack,
            upload_text=None,
            switched=switched if switched != feature.id else None,
            step_context=step_context,
            turn=turn,
            timer=timer,
            handed=True,
        ):
            yield event

    async def _start(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str,
        stack: ContextStack,
        timer: TurnTimer,
    ) -> AsyncIterator[Event]:
        """Staff picked a kind of help to start, after the assistant asked them what they need:
        it becomes the subject, and asks what they want from it (its `ask_for`, or an example).
        No model, no lookup: their next message is about it."""
        feature = await self._resolve(caller, conversation_id, text, feature_id)
        stack.push(feature.id, {})
        if stack.procedure_frame() is not None:
            await self.runner.pause(conversation_id)  # it waits below the new subject
        await self.conversations.append(conversation_id, Message("user", text))
        examples = (*feature.suggestions, *feature.route_examples)
        example = EXAMPLE.format(example=examples[0]) if examples else ""
        reply = feature.ask_for or START + example
        async for event in self._finish(
            caller, conversation_id, feature.id, _say(reply), timer=timer
        ):
            yield event
        await self.conversations.save_context(conversation_id, stack.as_dict())

    async def _back_to(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        stack: ContextStack,
        frame: Frame,
        timer: TurnTimer,
        stored: bool = False,
    ) -> AsyncIterator[Event]:
        """Staff clicked a subject to return to it: it comes to the top, and the next question
        is about it. No model, no lookup."""
        frame = stack.bring_to_top(frame.id)
        if (procedure := stack.procedure_frame()) is not None and procedure.id != frame.id:
            await self.runner.pause(conversation_id)
        if not stored:
            await self.conversations.append(conversation_id, Message("user", text))
        reply = f"Back to {self._describe(frame, None, stack)}. What would you like to know?"
        async for event in self._finish(
            caller, conversation_id, frame.feature_id, _say(reply), timer=timer
        ):
            yield event
        await self.conversations.save_context(conversation_id, stack.as_dict())

    async def _stop_quietly(
        self, caller: Caller, conversation_id: UUID, stack: ContextStack, frame: Frame
    ) -> AsyncIterator[Event]:
        """Another procedure starts: the open one is stopped first, saying so."""
        async for event in self.runner.stop(caller, conversation_id):
            yield event
        stack.drop(frame.id)

    def _same_kind(self, stack: ContextStack, reading: Reading) -> Frame | None:
        """The open subject a new subject's reading might really be about: the most recent one
        with the feature the reading chose (not a procedure)."""
        if reading.action != "new" or reading.feature_id is None:
            return None
        return next(
            (f for f in stack.frames if not f.procedure and f.feature_id == reading.feature_id),
            None,
        )

    def _only_it(self, frame: Frame, text: str) -> bool:
        """The message can only be about `frame`, not another of its kind: its feature needs a
        reference to look anything up (it asks for one), the message names none, and `frame`
        has one. Another transfer would have to be named; unnamed, a new subject could only ask
        "which one?" ("was it reversed?" after a transfer is that transfer)."""
        feature = self._feature(frame.feature_id)
        return bool(
            feature.ask_for
            and feature.prefetch
            and not planned_calls(feature, text, {})
            and planned_calls(feature, text, frame.entities)
        )

    async def _which_subject(
        self,
        text: str,
        stack: ContextStack,
        same_kind: Frame,
        reading: Reading,
        turn: Trace,
        timer: TurnTimer,
    ) -> Reading | None:
        """Same subject, or another of its kind? A second, two-way question; None if unclear."""
        subject = self._describe(same_kind, None, stack)
        with turn.span("same subject?", "chain", subject=subject) as span:
            same = await same_subject(
                TimedModel(TracedModel(self.model, span), timer), text, subject
            )
            span.set(same=same)
        if same is None:
            return None
        return Reading("continue", same_kind.id, by="model:same") if same else reading

    def _agent(self) -> Feature | None:
        """In agent mode, the feature that takes every new subject: the conversation."""
        return self._conversation() if self.turn_mode == "agent" else None

    def _conversation(self) -> Feature | None:
        """The pack's default feature, if it is a conversation (a template that is not a
        subject)."""
        try:
            feature = self.registry.get(self.router.default)
        except KeyError:
            return None
        return feature if _passing(self.templates.get(feature.template)) else None

    def _procedure_features(self) -> tuple[str, ...]:
        return tuple(f.id for f in self.registry if f.template == PROCEDURE_TEMPLATE)

    def _case(
        self, stack: ContextStack, procedure: Frame | None, feature: Feature
    ) -> dict[str, str]:
        """What a new subject takes from the case it comes out of: beside a procedure, the
        procedure's; else the subject staff were on. Only for a different feature (another of
        the same kind takes nothing, or one product's code would be looked up for the next),
        and only the entity types the new feature's lookups use: "what does that code mean?"
        after a failed transfer takes its failure code, nothing else."""
        source = procedure or stack.top
        if source is None or source.feature_id == feature.id:
            return {}
        wanted = {
            argument.entity
            for prefetch in feature.prefetch
            for argument in prefetch.arguments.values()
            if argument.entity
        }
        known = {**source.related, **source.entities}
        return {kind: value for kind, value in known.items() if kind in wanted}

    async def _waiting_step(self, conversation_id: UUID, stack: ContextStack) -> str:
        """For a question asked beside a procedure: its step, for searches."""
        if stack.procedure_frame() is None:
            return ""
        current = await self.runner.current(conversation_id)
        return f"{current[1].title}: {current[1].instruction}" if current else ""

    def _describe(
        self, frame: Frame, current: tuple[str, object] | None, stack: ContextStack | None = None
    ) -> str:
        """A frame in a few words, for the model reading the turn and for staff's chips:
        "Transaction lookup: transfer TX-0002", "Product lookup: Standard Savings (SAV-STD)"."""
        if frame.procedure and current is not None:
            title, step = current
            return f"procedure {title}, waiting on step {step.order}: {step.title}"  # type: ignore[attr-defined]
        about = []
        for kind, value in frame.entities.items():
            if kind == DOCUMENT:
                about.append(value)
                continue
            name = stack.name_of(kind, value) if stack is not None else None
            about.append(
                f"{name.title()} ({value})" if name else f"{kind.replace('_', ' ')} {value}"
            )
        title = self._feature(frame.feature_id).title
        return f"{title}{': ' + ', '.join(about) if about else ''}"

    def _feature(self, feature_id: str) -> Feature:
        try:
            return self.registry.get(feature_id)
        except KeyError:
            raise PolicyDenied(f"unknown feature {feature_id}") from None

    async def _audit_route(
        self, caller: Caller, conversation_id: UUID, feature: Feature, by: str, turn: Trace
    ) -> None:
        if not feature.allows(caller.role):
            raise PolicyDenied(f"role {caller.role} may not use {feature.id}")
        await self.audit.record(
            caller,
            "feature_routed",
            {
                "conversation_id": str(conversation_id),
                "chosen_by": f"context:{by}",
                "feature_id": feature.id,
            },
        )
        turn.set(feature=feature.id, routed_by=f"context:{by}")

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

    async def _resolve(
        self,
        caller: Caller,
        conversation_id: UUID,
        text: str,
        feature_id: str | None,
        turn: Trace | None = None,
        prefer: str | None = None,
        chosen_by: str | None = None,
        exclude: Sequence[str] = (),
        routed_by: str | None = None,
    ) -> Feature:
        """A new subject's feature: `feature_id` if given (staff locked it, reading the turn
        chose it: `chosen_by`, or the conversation handed the turn to it: `routed_by`), else in
        agent mode the conversation, else the router's choice."""
        turn = turn or Trace()
        detail: dict[str, object] = {"conversation_id": str(conversation_id)}
        if feature_id:
            try:
                feature = self.registry.get(feature_id)
            except KeyError:
                raise PolicyDenied(f"unknown feature {feature_id}") from None
            detail["chosen_by"] = routed_by or (f"context:{chosen_by}" if chosen_by else "client")
        elif (agent := self._agent()) is not None:
            feature = agent
            detail["chosen_by"] = "agent"
        else:
            with turn.span("route", "chain") as routing:
                try:
                    route = await self.router.route(
                        caller,
                        text,
                        TracedModel(self.model, routing),
                        prefer,
                        exclude,
                        guess=self.turn_mode != "hybrid" or self._conversation() is None,
                    )
                except LookupError:
                    raise PolicyDenied(f"no features for role {caller.role}") from None
                routing.set(
                    feature=route.feature.id,
                    routed_by=route.by,
                    score=route.score,
                    prefer=prefer,
                )
            feature = route.feature
            detail["chosen_by"] = route.by  # pattern, meaning, model... to find misroutes
            if prefer:
                detail["preferred"] = prefer
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
                elif isinstance(event, Clarify):
                    await self._audit_clarify(caller, conversation_id, event)
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


def _lacks_details(feature: Feature, text: str, entities: Mapping[str, str]) -> bool:
    """The feature asks for what its lookups need, and neither the question nor the subject
    gives any of it."""
    return bool(feature.ask_for and feature.prefetch and not planned_calls(feature, text, entities))


def _passing_ids(orchestrator: "Orchestrator") -> frozenset[str]:
    """The features that are conversation, not kinds of help."""
    return frozenset(
        f.id for f in orchestrator.registry if _passing(orchestrator.templates.get(f.template))
    )


def _passing(template: object) -> bool:
    """A template whose turns are not a subject of the conversation (small talk)."""
    return not getattr(template, "keeps_subject", True)


def _pointed_to(results: Sequence[ToolResult], types: Sequence[EntityType]) -> dict[str, str]:
    """What a turn's records point to (exact ids in their values)."""
    found: dict[str, str] = {}
    for result in results:
        if result.ok:
            for kind, value in values_in(result.data, types).items():
                found.setdefault(kind, value)
    return found


async def _say(text: str) -> AsyncIterator[Event]:
    yield TextDelta(text)


async def _once(event: Event | None) -> AsyncIterator[Event]:
    if event is not None:
        yield event


async def _then(first: AsyncIterator[Event], second: AsyncIterator[Event]) -> AsyncIterator[Event]:
    async for event in first:
        yield event
    async for event in second:
        yield event


def _timing(timer: TurnTimer) -> dict[str, int]:
    return {f"timing.{name}": value for name, value in timer.as_detail().items()}
