"""FakeToolClient: canned tool results for tests."""

from dataclasses import dataclass, replace

from core.types import Caller, ToolCall, ToolResult, ToolSpec


@dataclass(frozen=True)
class RecordedCall:
    caller: Caller
    call: ToolCall


class FakeToolClient:
    """Returns `results[tool_name]` for each call and records the caller and call."""

    def __init__(
        self,
        results: dict[str, ToolResult] | None = None,
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
        if result is None:
            return ToolResult(call_id=call.id, ok=False, error="not_found")
        return replace(result, call_id=call.id)
