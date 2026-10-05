"""The guard around every MCP tool, on a small made-up server reached in-process."""

from contextlib import asynccontextmanager

from mcp import Client

from core.policy.engine import PolicyEngine
from core.policy.rules import ALLOW, Decision, FieldRule, FunctionRule
from core.types import Caller, Citation, ToolCall
from mcp_servers.common.guard import GuardedServer, ToolInputError, ToolOutput
from providers.mcp.client import McpToolClient

SECRET = "s3cret"
RECORDS = {
    "R1": {"id": "R1", "team": "A", "note": "ok", "secret": "hidden", "items": [{"secret": "x"}]},
    "R2": {"id": "R2", "team": "B", "note": "other team"},
}


def same_team(caller: Caller, arguments: dict, record: dict | None) -> Decision:
    if record is None or record["team"] == caller.attributes.get("team"):
        return ALLOW
    return Decision(False, "team")


def records_server() -> GuardedServer:
    engine = PolicyEngine(
        [
            FunctionRule("records.get", same_team),
            FunctionRule("records.crash", lambda c, a, r: ALLOW),
            FunctionRule("records.check_date", lambda c, a, r: ALLOW),
        ],
        [FieldRule("records.get", hide=("secret",), unless_role=("supervisor",))],
    )
    server = GuardedServer("records", engine, SECRET)

    @server.tool("get", "Get a record by id.")
    async def get(caller: Caller, record_id: str) -> ToolOutput:
        record = RECORDS[record_id]  # KeyError -> not_found
        return ToolOutput(record, (Citation("record", "Record", record_id),), record=record)

    @server.tool("crash", "Always fails.")
    async def crash(caller: Caller) -> ToolOutput:
        raise RuntimeError("backend down")

    @server.tool("check_date", "Validates a date.")
    async def check_date(caller: Caller, day: str) -> ToolOutput:
        raise ToolInputError(f"{day} is not a date")

    @server.tool("unruled", "A tool with no access rule.")
    async def unruled(caller: Caller) -> ToolOutput:
        return ToolOutput("should never be seen")

    return server


def handler(role: str = "handler", team: str = "A") -> Caller:
    return Caller("S1", role, "staff", {"team": team})


@asynccontextmanager
async def connected(server: GuardedServer, secret: str = SECRET):
    async with McpToolClient({"records": server.mcp}, secret) as client:
        yield client


async def call(tool: str, caller: Caller | None = None, server=None, secret=SECRET, **arguments):
    async with connected(server or records_server(), secret) as client:
        return await client.call(caller or handler(), ToolCall("1", f"records.{tool}", arguments))


async def test_allowed_call_returns_filtered_data_and_citations() -> None:
    result = await call("get", record_id="R1")
    assert result.ok
    assert result.data == {"id": "R1", "team": "A", "note": "ok", "items": [{}]}
    assert result.citations == (Citation("record", "Record", "R1"),)


async def test_role_exempt_from_a_field_rule_sees_the_field() -> None:
    result = await call("get", handler("supervisor"), record_id="R1")
    assert result.data["secret"] == "hidden"


async def test_scope_rule_is_checked_on_the_fetched_record() -> None:
    result = await call("get", record_id="R2")
    assert (result.ok, result.error, result.data) == (False, "denied", None)


async def test_tool_without_a_rule_is_denied() -> None:
    assert (await call("unruled")).error == "denied"


async def test_wrong_secret_is_denied_before_the_tool_runs() -> None:
    assert (await call("get", secret="forged", record_id="R1")).error == "denied"


async def test_call_without_a_token_is_denied() -> None:
    async with Client(records_server().mcp) as raw:
        result = await raw.call_tool("get", {"record_id": "R1"})
    assert result.structured_content == {"ok": False, "error": "denied"}


async def test_not_found_crash_and_bad_input() -> None:
    assert (await call("get", record_id="R9")).error == "not_found"
    assert (await call("crash")).error == "upstream_error"
    bad = await call("check_date", day="31/02")
    assert bad.error == "invalid_arguments"
    assert bad.data == ["31/02 is not a date"]


async def test_the_model_never_sees_a_caller_parameter() -> None:
    async with connected(records_server()) as client:
        specs = {s.name: s for s in await client.list_tools()}
    schema = specs["records.get"].input_schema
    assert set(schema["properties"]) == {"record_id"}
    assert schema["required"] == ["record_id"]
    assert specs["records.crash"].input_schema.get("properties", {}) == {}


async def test_tools_registered_around_the_guard_are_reported() -> None:
    server = records_server()
    assert await server.unguarded_tools() == []

    @server.mcp.tool(name="sneaky")
    async def sneaky() -> str:
        return "unguarded"

    assert await server.unguarded_tools() == ["sneaky"]
    assert "records.sneaky" in await server.tool_names()
