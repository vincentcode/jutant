"""A turn as a trace: the span tree, and what content a trace may hold."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

from core.observability import TraceContent
from core.types import ArgumentSource, ModelReply, Prefetch, ToolCall, ToolResult
from providers.llm.fake import FakeModel
from tests.builders import FEATURES, collect_events, doc_result, make_rig, spec, teller

ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {"reference": {"type": "string"}},
    "required": ["reference"],
}


@dataclass
class Recorded:
    name: str
    kind: str
    attributes: dict[str, Any]
    parent: "Recorded | None"
    failed: str | None = None
    children: list["Recorded"] = field(default_factory=list)

    def set(self, attributes: Mapping[str, Any]) -> None:
        self.attributes.update(attributes)

    def fail(self, reason: str) -> None:
        self.failed = reason

    def carrier(self) -> dict[str, str]:
        return {"traceparent": f"span:{id(self)}"}


class RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[Recorded] = []

    @contextmanager
    def span(self, name, kind, attributes, parent) -> Iterator[Recorded]:
        span = Recorded(name, kind, dict(attributes), parent)
        if parent is not None:
            parent.children.append(span)
        self.spans.append(span)
        yield span

    def remote(self, carrier):
        return Recorded("remote parent", "tool", dict(carrier), None)

    def named(self, name: str) -> list[Recorded]:
        return [s for s in self.spans if s.name == name]


async def traced_rig(model, content=False, **kwargs):
    rig = await make_rig(model, **kwargs)
    tracer = RecordingTracer()
    rig.orchestrator.tracer = tracer
    rig.orchestrator.trace_content = TraceContent(include=content)
    return rig, tracer


def searched(*features):
    prefetch = Prefetch("documents.search", {"query": ArgumentSource(question=True)})
    return tuple(replace(f, prefetch=(prefetch,)) if f.id == "policy_qa" else f for f in FEATURES)


async def test_a_turn_is_one_tree_of_spans() -> None:
    model = FakeModel(replies=[ModelReply("policy_qa"), ModelReply("Both need ID.")])
    rig, tracer = await traced_rig(
        model,
        results={"documents.search": doc_result("KYC Policy", "4.2")},
        features=searched(),
    )
    conversation = uuid4()
    await collect_events(rig.orchestrator.ask(teller(), conversation, "KYC for joint accounts?"))

    [turn] = tracer.named("turn")
    assert turn.parent is None and turn.kind == "agent"
    assert turn.attributes["session"] == str(conversation)
    assert turn.attributes["feature"] == "policy_qa" and turn.attributes["routed_by"] == "model"
    assert turn.attributes["timing.model_calls"] == 1
    assert [(c.name, c.kind) for c in turn.children] == [
        ("route", "chain"),
        ("documents.search", "tool"),
        ("model", "llm"),
    ]
    [route] = tracer.named("route")
    assert [c.kind for c in route.children] == ["llm"]  # the router's model call, under routing
    tool = tracer.named("documents.search")[0]
    assert tool.attributes["tool.ok"] is True and tool.attributes["citations"] == 1


async def test_without_content_tracing_no_prompt_or_answer_is_recorded() -> None:
    model = FakeModel(replies=[ModelReply("Both need ID.")])
    rig, tracer = await traced_rig(
        model, results={"documents.search": doc_result("KYC Policy", "4.2")}, features=searched()
    )
    await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Account 0011223344?", "policy_qa")
    )
    recorded = {k for s in tracer.spans for k in s.attributes}
    assert not recorded & {"input", "output", "messages", "reply"}
    # Tool arguments are recorded as the audit log records them: masked.
    tool = tracer.named("documents.search")[0]
    assert tool.attributes["tool.arguments"] == {"query": "Account ******3344?"}


async def test_with_content_tracing_prompts_and_answers_are_recorded_masked() -> None:
    model = FakeModel(replies=[ModelReply("Account 0011223344 is a savings account.")])
    rig, tracer = await traced_rig(
        model,
        content=True,
        results={"documents.search": doc_result("KYC Policy", "4.2")},
        features=searched(),
    )
    await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "What is 0011223344?", "policy_qa")
    )
    [turn] = tracer.named("turn")
    assert turn.attributes["input"] == "What is ******3344?"
    assert turn.attributes["output"] == "Account ******3344 is a savings account."
    llm = tracer.named("model")[0]
    assert all("0011223344" not in m["content"] for m in llm.attributes["messages"])
    assert llm.attributes["reply"] == "Account ******3344 is a savings account."


async def test_a_refusal_marks_the_turn_failed() -> None:
    status = Prefetch("transactions.get_status", {"reference": ArgumentSource(match=r"TX-\d+")})
    features = tuple(
        replace(f, prefetch=(status,)) if f.id == "transaction_lookup" else f for f in FEATURES
    )
    rig, tracer = await traced_rig(
        FakeModel(),
        results={"transactions.get_status": ToolResult("", ok=False, error="denied")},
        features=features,
        specs=[spec("transactions.get_status", ACCOUNT_SCHEMA)],
    )
    await collect_events(
        rig.orchestrator.ask(teller(), uuid4(), "Why did TX-0002 fail?", "transaction_lookup")
    )
    [turn] = tracer.named("turn")
    assert turn.failed == "denied" and turn.attributes["failed"] == "denied"
    assert tracer.named("transactions.get_status")[0].attributes["tool.error"] == "denied"


async def test_playbook_steps_are_spans() -> None:
    rig, tracer = await traced_rig(FakeModel(replies=[ModelReply("blocked_card")]))
    await collect_events(rig.orchestrator.ask(teller(), uuid4(), "card blocked", "troubleshooting"))
    [step] = tracer.named("playbook step")
    assert step.attributes["playbook"] == "blocked_card" and step.attributes["step"] == 1


async def test_the_model_s_tool_calls_are_recorded_masked() -> None:
    call = ToolCall("1", "documents.search", {"query": "account 0011223344"})
    model = FakeModel(replies=[ModelReply(None, (call,)), ModelReply("Done.")])
    rig, tracer = await traced_rig(
        model, results={"documents.search": doc_result("KYC Policy", "4.2")}
    )
    await collect_events(rig.orchestrator.ask(teller(), uuid4(), "kyc?", "policy_qa"))
    first = tracer.named("model")[0]
    assert first.attributes["reply.tool_calls"] == [
        {"name": "documents.search", "arguments": {"query": "account ******3344"}}
    ]


async def test_a_tool_call_hands_its_span_to_the_server() -> None:
    model = FakeModel(replies=[ModelReply("Both need ID.")])
    rig, tracer = await traced_rig(
        model, results={"documents.search": doc_result("KYC Policy", "4.2")}, features=searched()
    )
    await collect_events(rig.orchestrator.ask(teller(), uuid4(), "KYC?", "policy_qa"))
    [tool_span] = tracer.named("documents.search")
    assert rig.tools.calls[0].trace_context == {"traceparent": f"span:{id(tool_span)}"}


async def test_an_answer_is_stored_with_its_turn_s_trace_for_feedback() -> None:
    model = FakeModel(replies=[ModelReply("Both need ID.")])
    rig, tracer = await traced_rig(
        model, results={"documents.search": doc_result("KYC Policy", "4.2")}, features=searched()
    )
    conversation = uuid4()
    await collect_events(rig.orchestrator.ask(teller(), conversation, "KYC?", "policy_qa"))
    [turn] = tracer.named("turn")
    answer = rig.conversations.messages[conversation][-1]
    assert answer.trace_context == turn.carrier()
