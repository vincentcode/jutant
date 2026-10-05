"""PlaybookRunner: walks a staff member through a procedure, one step at a time.

The playbook decides the next step (from `next_on` or the step order); the model never does.
The model is used only to map a free-text reply onto one of a step's listed choices.
"cancel" or "stop" abandons the run.
"""

import re
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import UUID

from core.events import Event, PlaybookStepShown, TextDelta
from core.features.matching import Option, choose, parse_choice
from core.playbooks.filtering import next_step, steps_for
from core.ports import AuditSink, ModelProvider, PlaybookStore
from core.types import Caller, PlaybookRunState, PlaybookStep

CANCEL_WORDS = frozenset({"cancel", "stop"})
CONFIRM_WORDS = frozenset({"confirm", "done", "yes", "y", "ok", "okay", "next", "completed"})

FINISHED = "Procedure complete."
STOPPED = "Stopped the procedure."
NO_STEPS = "This procedure has no steps for you."


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
        async for event in self._show(conversation_id, state, steps, steps[0]):
            yield event

    async def abandon(self, caller: Caller, conversation_id: UUID) -> None:
        """End the conversation's run, if there is one, without finishing it."""
        state = await self.store.get_run(conversation_id)
        if state is None:
            return
        await self.store.save_run(conversation_id, replace(state, status="abandoned"))
        await self._audit_step(caller, conversation_id, state, "abandoned")

    async def advance(
        self, caller: Caller, conversation_id: UUID, user_input: str
    ) -> AsyncIterator[Event]:
        state = await self.store.get_run(conversation_id)
        if state is None:
            return
        playbook = await self.store.get(state.playbook_id)
        steps = steps_for(playbook, caller.audience)
        current = next((s for s in steps if s.order == state.current_order), None)
        text = user_input.strip()

        if text.lower().rstrip(".!") in CANCEL_WORDS or current is None:
            await self.abandon(caller, conversation_id)
            yield TextDelta(STOPPED)
            return

        answer = await self._interpret(current, text)
        if answer is None:
            yield TextDelta(_hint(current))
            yield PlaybookStepShown(state.playbook_id, current)
            return

        state = replace(state, answers={**state.answers, current.order: answer})
        await self._audit_step(caller, conversation_id, state, answer)
        following = next_step(steps, current, answer)
        if following is None:
            await self.store.save_run(conversation_id, replace(state, status="completed"))
            yield TextDelta(FINISHED)
            return
        async for event in self._show(conversation_id, state, steps, following):
            yield event

    async def _show(
        self,
        conversation_id: UUID,
        state: PlaybookRunState,
        steps: tuple[PlaybookStep, ...],
        step: PlaybookStep | None,
    ) -> AsyncIterator[Event]:
        """Show `step`, then any `none` steps after it, which need no reply."""
        while step is not None and step.expects == "none":
            yield PlaybookStepShown(state.playbook_id, step)
            step = next_step(steps, step, "")
        if step is None:
            await self.store.save_run(conversation_id, replace(state, status="completed"))
            yield TextDelta(FINISHED)
            return
        await self.store.save_run(conversation_id, replace(state, current_order=step.order))
        yield PlaybookStepShown(state.playbook_id, step)

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


def _hint(step: PlaybookStep) -> str:
    if step.expects == "choice":
        return "Please choose one of: " + ", ".join(c.replace("_", " ") for c in step.choices) + "."
    if step.expects == "confirm":
        return "Reply 'done' when this step is complete, or 'cancel' to stop."
    return "Please reply to this step, or 'cancel' to stop."
