"""ToolGateway: validate, attach caller, dispatch.

1. Tool must be in `feature.tools` (else InvalidToolCall).
2. Tool must exist in the catalog (else UnknownTool).
3. Validate arguments against the tool's JSON schema.
4. Strip identity-like arguments.
5. `ToolClient.call(caller, call)`.
6. Audit `tool_called`, `tool_denied` or `tool_failed`.
"""

from core.ports import AuditSink, ToolClient
from core.tools.catalog import ToolCatalog
from core.types import Caller, Feature, ToolCall, ToolResult


class ToolGateway:
    def __init__(self, client: ToolClient, catalog: ToolCatalog, audit: AuditSink):
        self.client = client
        self.catalog = catalog
        self.audit = audit

    async def execute(self, caller: Caller, feature: Feature, call: ToolCall) -> ToolResult:
        raise NotImplementedError
