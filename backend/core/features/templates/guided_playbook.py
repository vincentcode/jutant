"""`guided_playbook` template.

Picks the playbook that matches the staff member's problem, then hands control to the
PlaybookRunner. Later turns in the conversation go straight to the runner until the playbook
finishes or is cancelled.
"""

from collections.abc import AsyncIterator

from core.events import Event, TextDelta
from core.features.matching import Option, choose
from core.features.templates.base import FeatureContext

INSTRUCTION = "Choose the procedure that matches the problem described."


class GuidedPlaybookTemplate:
    id = "guided_playbook"
    requires_citation = False

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        playbooks = await ctx.playbooks.list()
        options = [Option(p.id, f"{p.title}. {p.description}") for p in playbooks]
        chosen = await choose(ctx.model, INSTRUCTION, ctx.question, options)
        if chosen is None:
            titles = ", ".join(p.title for p in playbooks) or "none"
            yield TextDelta(f"Which procedure do you need? Available: {titles}.")
            return
        async for event in ctx.runner.start(
            ctx.caller, ctx.conversation_id, chosen, ctx.feature.id
        ):
            yield event
