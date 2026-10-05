"""FakeToolClient: canned tool results for tests."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from core.types import Caller, ToolCall, ToolResult, ToolSpec

# A canned result, or a function of the call's arguments for results that depend on them.
Result = ToolResult | Callable[[dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class RecordedCall:
    caller: Caller
    call: ToolCall


class FakeToolClient:
    """Returns `results[tool_name]` for each call (called with the arguments, if a function)
    and records the caller and call."""

    def __init__(
        self,
        results: dict[str, Result] | None = None,
        specs: list[ToolSpec] | None = None,
    ):
        self.results = results or {}
        self.specs = (
            specs
            if specs is not None
            else [ToolSpec(name, name, {"type": "object"}) for name in self.results]
        )
        self.calls: list[RecordedCall] = []

    async def list_tools(self) -> list[ToolSpec]:
        return list(self.specs)

    async def call(self, caller: Caller, call: ToolCall) -> ToolResult:
        self.calls.append(RecordedCall(caller, call))
        result = self.results.get(call.name)
        if callable(result):
            result = result(call.arguments)
        if result is None:
            return ToolResult(call_id=call.id, ok=False, error="not_found")
        return replace(result, call_id=call.id)
