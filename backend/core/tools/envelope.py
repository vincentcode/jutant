"""The shape every MCP tool result takes on the wire, shared by the servers and the client.

A tool returns `{"ok": true, "data": ..., "citations": [...]}` or
`{"ok": false, "error": "<code>"}`. The guard around each server tool writes it; the MCP client
reads it back into a `ToolResult`. Keeping both directions here means they cannot drift apart.

The caller's signed token travels in the request's `_meta` under `CALLER_META_KEY`, never as a
tool argument, so the model never sees or supplies it.
"""

from dataclasses import asdict
from typing import Any, get_args

from core.types import Citation, ToolError, ToolResult

CALLER_META_KEY = "jutant/caller"
ERRORS = frozenset(get_args(ToolError))


def ok(data: Any, citations: tuple[Citation, ...] | list[Citation] = ()) -> dict[str, Any]:
    return {"ok": True, "data": data, "citations": [asdict(c) for c in citations]}


def error(code: ToolError, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": False, "error": code}
    if detail is not None:
        body["detail"] = detail
    return body


def to_result(call_id: str, payload: Any) -> ToolResult:
    """Read an envelope back into a ToolResult. Anything malformed is an upstream error."""
    if not isinstance(payload, dict) or "ok" not in payload:
        return ToolResult(call_id, ok=False, error="upstream_error")
    if payload["ok"]:
        try:
            citations = tuple(Citation(**c) for c in payload.get("citations") or ())
        except TypeError:
            return ToolResult(call_id, ok=False, error="upstream_error")
        return ToolResult(call_id, ok=True, data=payload.get("data"), citations=citations)
    code = payload.get("error")
    return ToolResult(
        call_id,
        ok=False,
        data=payload.get("detail"),
        error=code if code in ERRORS else "upstream_error",
    )
