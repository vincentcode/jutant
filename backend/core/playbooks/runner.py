"""PlaybookRunner: walks a staff member through a procedure, one step at a time.

The playbook decides the next step (from `next_on` or the step order); the model never does.
The model is used only to map a free-text reply onto one of a step's listed choices.
"cancel" or "stop" abandons the run.

A step can look a record up with the reply (`lookup`): "TX-0002" fetches that transfer through
the given `lookup` function, which makes the call as any tool call is made (feature check,
policy, audit, trace). The record is kept with the run, and later steps use it:

- a choice step with `answer_from: 1.status` is answered by the record, when its value is one
  of the step's choices, so the procedure takes the right branch without asking;
- an instruction can quote the record: "Failed: {1.failure_reason}".

A reference that is not found, or a record the caller may not see, keeps the run on the step.

A run can be paused while staff ask about something else, and resumed on its step. It ends only
when staff stop it (or it completes), and stopping it says so.
"""

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from core.events import Event, PlaybookStepShown, TextDelta, ToolFinished, ToolStarted
from core.features.matching import Option, choose, parse_choice
from core.playbooks.filtering import next_step, steps_for
from core.ports import AuditSink, ModelProvider, PlaybookStore
from core.types import Caller, PlaybookRunState, PlaybookStep, ToolCall, ToolResult

CANCEL_WORDS = frozenset({"cancel", "stop"})
CONFIRM_WORDS = frozenset({"confirm", "done", "yes", "y", "ok", "okay", "next", "completed"})
PLACEHOLDER = re.compile(r"\{(\d+)\.(\w+)\}")

FINISHED = "Procedure complete."
STOPPED = "Stopped the procedure."
STOPPED_NAMED = "Stopped the {title} procedure."
NO_STEPS = "This procedure has no steps for you."
UNKNOWN = "unknown"

Lookup = Callable[[ToolCall], Awaitable[ToolResult]]


class PlaybookRunner:
    def __init__(self, store: PlaybookStore, audit: AuditSink, model: ModelProvider | None = None):
        self.store = store
        self.audit = audit
        self.model = model

    async def start(
        self, caller: Caller, conversation_id: UUID, playbook_id: str, feature_id: str = ""
    ) -> AsyncIterator[Event]:
        playbook = await self.store.get(playbook_id)
        steps = steps_for(playbook, caller.audience)
        await self.audit.record(
            caller,
            "playbook_started",
            {"conversation_id": str(conversation_id), "playbook_id": playbook_id},
        )
        if not steps:
            yield TextDelta(NO_STEPS)
            return
        state = PlaybookRunState(playbook_id, steps[0].order, {}, "active", feature_id)
        async for event in self._show(
            caller, conversation_id, state, steps, steps[0], playbook.title
        ):
            yield event

    async def abandon(self, caller: Caller, conversation_id: UUID) -> None:
        """End the conversation's run, if there is one, without finishing it."""
        state = await self.store.get_run(conversation_id)
        if state is None:
            return
        await self.store.save_run(conversation_id, replace(state, status="abandoned"))
        await self._audit_step(caller, conversation_id, state, "abandoned")

    async def advance(
        self,
        caller: Caller,
        conversation_id: UUID,
        user_input: str,
        lookup: Lookup | None = None,
        choice: str | None = None,
    ) -> AsyncIterator[Event]:
        """Take `user_input` as the answer to the current step. `choice`: the option it gives,
        when that is already known (read with the message's intent)."""
        state = await self.store.get_run(conversation_id)
        if state is None:
            return
        playbook = await self.store.get(state.playbook_id)
        steps = steps_for(playbook, caller.audience)
        current = next((s for s in steps if s.order == state.current_order), None)
        text = user_input.strip()
        state = replace(state, paused=False)

        if text.lower().rstrip(".!") in CANCEL_WORDS or current is None:
            await self.abandon(caller, conversation_id)
            yield TextDelta(STOPPED_NAMED.format(title=playbook.title))
            return

        answer = choice if _given(current, choice) else await self._interpret(current, text)
        if answer is None:
            yield TextDelta(_hint(current))
            yield PlaybookStepShown(state.playbook_id, _filled(current, state), playbook.title)
            return

        if current.lookup is not None and lookup is not None:
            value = _looked_up_value(current, text)
            if value is None:
                yield TextDelta(_lookup_hint(current))
                yield PlaybookStepShown(state.playbook_id, _filled(current, state), playbook.title)
                return
            call = ToolCall(
                f"step_{uuid4().hex[:8]}", current.lookup.tool, {current.lookup.argument: value}
            )
            yield ToolStarted(call)
            result = await lookup(call)
            yield ToolFinished(result)
            if not result.ok or not isinstance(result.data, dict):
                yield TextDelta(_lookup_failed(result, value))
                yield PlaybookStepShown(state.playbook_id, _filled(current, state), playbook.title)
                return
            state = replace(state, facts={**state.facts, current.order: result.data})
            answer = value

        state = replace(state, answers={**state.answers, current.order: answer})
        await self._audit_step(caller, conversation_id, state, answer)
        following = next_step(steps, current, answer)
        async for event in self._show(
            caller, conversation_id, state, steps, following, playbook.title
        ):
            yield event

    async def current(self, conversation_id: UUID) -> tuple[str, PlaybookStep] | None:
        """The run's playbook title and the step it waits on, if a run is in progress."""
        state = await self.store.get_run(conversation_id)
        if state is None:
            return None
        playbook = await self.store.get(state.playbook_id)
        step = next((s for s in playbook.steps if s.order == state.current_order), None)
        return (playbook.title, step) if step is not None else None

    async def pause(self, conversation_id: UUID) -> None:
        state = await self.store.get_run(conversation_id)
        if state is not None and not state.paused:
            await self.store.save_run(conversation_id, replace(state, paused=True))

    async def unpause(self, conversation_id: UUID) -> None:
        """The run is the conversation's subject again (a word in passing went above it), without
        showing its step again."""
        state = await self.store.get_run(conversation_id)
        if state is not None and state.paused:
            await self.store.save_run(conversation_id, replace(state, paused=False))

    async def resume(self, conversation_id: UUID) -> AsyncIterator[Event]:
        """Show the step the run waits on again."""
        state = await self.store.get_run(conversation_id)
        if state is None:
            return
        playbook = await self.store.get(state.playbook_id)
        state = replace(state, paused=False)
        await self.store.save_run(conversation_id, state)
        step = next((s for s in playbook.steps if s.order == state.current_order), None)
        if step is not None:
            yield PlaybookStepShown(state.playbook_id, _filled(step, state), playbook.title)

    async def stop(self, caller: Caller, conversation_id: UUID) -> AsyncIterator[Event]:
        state = await self.store.get_run(conversation_id)
        if state is None:
            return
        playbook = await self.store.get(state.playbook_id)
        await self.abandon(caller, conversation_id)
        yield TextDelta(STOPPED_NAMED.format(title=playbook.title))

    async def _show(
        self,
        caller: Caller,
        conversation_id: UUID,
        state: PlaybookRunState,
        steps: tuple[PlaybookStep, ...],
        step: PlaybookStep | None,
        title: str = "",
    ) -> AsyncIterator[Event]:
        """Show `step`. Steps that need no reply (`none`), and choices a looked-up record
        answers, are shown or answered in turn, until one needs the staff member."""
        while step is not None:
            if step.expects == "none":
                yield PlaybookStepShown(state.playbook_id, _filled(step, state), title)
                step = next_step(steps, step, "")
                continue
            answer = _answer_from_record(step, state)
            if answer is None:
                break
            yield PlaybookStepShown(state.playbook_id, _filled(step, state), title, answer)
            state = replace(
                state, current_order=step.order, answers={**state.answers, step.order: answer}
            )
            await self._audit_step(caller, conversation_id, state, answer)
            step = next_step(steps, step, answer)
        if step is None:
            await self.store.save_run(conversation_id, replace(state, status="completed"))
            yield TextDelta(FINISHED)
            return
        state = replace(state, current_order=step.order)
        await self.store.save_run(conversation_id, state)
        yield PlaybookStepShown(state.playbook_id, _filled(step, state), title)

    async def _interpret(self, step: PlaybookStep, text: str) -> str | None:
        """The answer `text` gives to `step`, or None if it does not answer it."""
        if not text:
            return None
        if step.expects == "confirm":
            return "confirm" if text.lower().rstrip(".!") in CONFIRM_WORDS else None
        if step.expects == "choice":
            normalised = re.sub(r"[\s-]+", "_", text.lower())
            exact = parse_choice(normalised, step.choices)
            if exact or self.model is None:
                return exact
            options = [Option(c, c.replace("_", " ")) for c in step.choices]
            return await choose(
                self.model, f"Which option does this reply mean? {step.instruction}", text, options
            )
        return text

    async def _audit_step(
        self, caller: Caller, conversation_id: UUID, state: PlaybookRunState, answer: str
    ) -> None:
        await self.audit.record(
            caller,
            "playbook_step",
            {
                "conversation_id": str(conversation_id),
                "playbook_id": state.playbook_id,
                "order": state.current_order,
                "answer": answer,
            },
        )


def _given(step: PlaybookStep, choice: str | None) -> bool:
    """`choice` already answers `step` (read with the message's intent): one of its options,
    or "confirm" for a step that asks to confirm."""
    return choice is not None and (
        choice in step.choices or (step.expects == "confirm" and choice == "confirm")
    )


def _looked_up_value(step: PlaybookStep, text: str) -> str | None:
    """What the reply gives the lookup: the pattern's first group (or match), or the reply."""
    assert step.lookup is not None
    if step.lookup.pattern is None:
        return text
    found = re.search(step.lookup.pattern, text)
    if found is None:
        return None
    return found.group(1) if found.re.groups else found.group(0)


def _answer_from_record(step: PlaybookStep, state: PlaybookRunState) -> str | None:
    """The choice a looked-up record makes for `step`, if it names one of the choices."""
    if step.expects != "choice" or not step.answer_from:
        return None
    order, _, name = step.answer_from.partition(".")
    value = state.facts.get(int(order), {}).get(name)
    if value is None:
        return None
    return parse_choice(re.sub(r"[\s-]+", "_", str(value).lower()), step.choices)


def _filled(step: PlaybookStep, state: PlaybookRunState) -> PlaybookStep:
    """The step with any {1.field} in its title and instruction replaced from the records."""
    if not state.facts or "{" not in step.instruction + step.title:
        return step

    def value(match: re.Match[str]) -> str:
        found: Any = state.facts.get(int(match.group(1)), {}).get(match.group(2))
        return UNKNOWN if found in (None, "") else str(found)

    return replace(
        step,
        title=PLACEHOLDER.sub(value, step.title),
        instruction=PLACEHOLDER.sub(value, step.instruction),
    )


def _lookup_hint(step: PlaybookStep) -> str:
    assert step.lookup is not None
    what = step.lookup.argument.replace("_", " ")
    return f"I could not find a {what} in that. Please reply with the {what}, or 'cancel' to stop."


def _lookup_failed(result: ToolResult, value: str) -> str:
    if result.error == "not_found":
        return f"No record was found for {value}. Check it and reply again, or 'cancel' to stop."
    if result.error == "denied":
        return f"You don't have access to {value}. Reply with another, or 'cancel' to stop."
    return "The lookup did not work just now. Try again in a moment, or 'cancel' to stop."


def _hint(step: PlaybookStep) -> str:
    if step.expects == "choice":
        return "Please choose one of: " + ", ".join(c.replace("_", " ") for c in step.choices) + "."
    if step.expects == "confirm":
        return "Reply 'done' when this step is complete, or 'cancel' to stop."
    return "Please reply to this step, or 'cancel' to stop."
