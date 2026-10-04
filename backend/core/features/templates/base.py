"""What every feature template implements, and the context a template runs with.

A template is the behaviour behind a feature (answer from documents, look up a record, run a
playbook...). A pack turns a template into a feature by giving it a prompt and a list of tools.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from core.events import Event
from core.ports import AuditSink, ModelProvider, PlaybookStore
from core.types import Caller, Feature, Message, ToolResult

if TYPE_CHECKING:
    from core.tools.gateway import ToolGateway


@dataclass
class FeatureContext:
    caller: Caller
    conversation_id: UUID
    feature: Feature
    question: str
    messages: list[Message]  # the built prompt window
    model: ModelProvider
    gateway: "ToolGateway"
    playbooks: PlaybookStore
    audit: AuditSink
    max_steps: int
    results: list[ToolResult] = field(default_factory=list)  # filled during the run
    upload_text: Callable[[], str] | None = None  # extraction feature only


class FeatureTemplate(Protocol):
    id: str
    requires_citation: bool

    def run(self, ctx: FeatureContext) -> AsyncIterator[Event]: ...


async def tool_loop(ctx: FeatureContext) -> AsyncIterator[Event]:
    """The default template behaviour: model -> tool calls -> model, up to `max_steps`."""
    raise NotImplementedError
    yield  # pragma: no cover
