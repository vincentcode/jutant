"""`guided_playbook` template.

Selects a playbook, then hands control to PlaybookRunner.
"""

from collections.abc import AsyncIterator

from core.events import Event
from core.features.templates.base import FeatureContext


class GuidedPlaybookTemplate:
    id = "guided_playbook"
    requires_citation = False

    async def run(self, ctx: FeatureContext) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # pragma: no cover
