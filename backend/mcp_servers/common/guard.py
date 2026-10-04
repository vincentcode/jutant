"""@guarded_tool: policy check and field filter around every MCP tool.

1. Resolve the caller from the request.
2. `engine.authorize(caller, tool, arguments)`; deny returns a `denied` error.
3. Run the tool to fetch data.
4. If the rule needs the record (scope checks), authorize again with `record=data`.
5. `engine.filter(caller, tool, data)`.
6. Return `{data, citations}`.

A tool without this decorator fails the contract test.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from core.policy.engine import PolicyEngine

ToolFn = Callable[..., Awaitable[Any]]
GUARDED_ATTR = "__jutant_guarded__"


def guarded_tool(name: str, engine: PolicyEngine, secret: str) -> Callable[[ToolFn], ToolFn]:
    def decorate(fn: ToolFn) -> ToolFn:
        raise NotImplementedError

    return decorate
