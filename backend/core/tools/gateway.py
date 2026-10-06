"""ToolGateway: every tool call from the model passes through here before it reaches a server.

1. The tool must be one the routed feature may use (else InvalidToolCall).
2. The tool must exist in the catalog (else UnknownTool).
3. Identity-like arguments are removed; the caller travels separately, signed.
4. The arguments are checked against the tool's JSON schema. Problems come back as an
   `invalid_arguments` result so the model can correct the call.
5. The call goes to the tool client with the caller attached.
6. The outcome is audited as `tool_called`, `tool_denied` or `tool_failed`.

Identity arguments are removed before validation, so a model that adds `user_id` to a tool
with a strict schema still gets its call through without that argument.
"""

from collections.abc import Mapping
from typing import Any

from core.errors import InvalidToolCall, UnknownTool
from core.ports import AuditSink, ToolClient
from core.tools.catalog import ToolCatalog
from core.tools.validation import strip_identity, validate_arguments
from core.types import Caller, Feature, ToolCall, ToolResult


class ToolGateway:
    def __init__(self, client: ToolClient, catalog: ToolCatalog, audit: AuditSink):
        self.client = client
        self.catalog = catalog
        self.audit = audit

    async def execute(
        self,
        caller: Caller,
        feature: Feature,
        call: ToolCall,
        conversation_id: str | None = None,
        trace_context: Mapping[str, str] | None = None,
    ) -> ToolResult:
        detail: dict[str, Any] = {
            "tool": call.name,
            "feature_id": feature.id,
            "conversation_id": conversation_id,
        }
        if call.name not in feature.tools:
            await self.audit.record(caller, "tool_failed", {**detail, "error": "not_permitted"})
            raise InvalidToolCall(f"{call.name} is not a tool of feature {feature.id}")
        spec = self.catalog.get(call.name)
        if spec is None:
            await self.audit.record(caller, "tool_failed", {**detail, "error": "unknown_tool"})
            raise UnknownTool(call.name)

        arguments = strip_identity(call.arguments)
        detail["arguments"] = arguments
        problems = validate_arguments(arguments, spec.input_schema)
        if problems:
            await self.audit.record(
                caller,
                "tool_failed",
                {**detail, "error": "invalid_arguments", "problems": problems},
            )
            return ToolResult(
                call_id=call.id, ok=False, data={"problems": problems}, error="invalid_arguments"
            )

        result = await self.client.call(
            caller, ToolCall(call.id, call.name, arguments), trace_context
        )
        if result.ok:
            await self.audit.record(caller, "tool_called", detail)
        elif result.error == "denied":
            await self.audit.record(caller, "tool_denied", detail)
        else:
            await self.audit.record(caller, "tool_failed", {**detail, "error": result.error})
        return result
