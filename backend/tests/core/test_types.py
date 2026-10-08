"""Smoke tests: the core types, the six templates and the test fakes behave as expected."""

from dataclasses import FrozenInstanceError

import pytest

from core.features.templates import TEMPLATES
from core.types import Caller, Feature, ModelReply, ToolCall, ToolResult
from providers.llm.fake import FakeModel
from providers.mcp.fake import FakeToolClient
from tests.fakes import InMemoryAudit, InMemoryConversationStore


def test_types_are_frozen(teller: Caller) -> None:
    with pytest.raises(FrozenInstanceError):
        teller.role = "branch_manager"  # type: ignore[misc]


def test_feature_with_no_roles_allows_everyone() -> None:
    feature = Feature("f", "document_qa", "F", "d", "p", (), ())
    restricted = Feature("g", "record_summary", "G", "d", "p", (), ("branch_manager",))
    assert feature.allows("teller")
    assert not restricted.allows("teller")


def test_templates_registered() -> None:
    assert set(TEMPLATES) == {
        "document_qa",
        "record_lookup",
        "record_summary",
        "guided_playbook",
        "document_extraction",
        "checklist",
        "conversation",
    }
    assert TEMPLATES["document_qa"].requires_citation
    assert not TEMPLATES["guided_playbook"].requires_citation
    assert not TEMPLATES["conversation"].requires_citation


async def test_fake_model_replays_and_records() -> None:
    model = FakeModel(replies=[ModelReply(text="hello")])
    reply = await model.chat([], [])
    assert reply.text == "hello"
    assert len(model.calls) == 1


async def test_fake_tool_client_records_caller(teller: Caller) -> None:
    tools = FakeToolClient(results={"documents.search": ToolResult(call_id="", ok=True, data=[])})
    result = await tools.call(teller, ToolCall("1", "documents.search", {"query": "kyc"}))
    assert result.ok and result.call_id == "1"
    assert tools.calls[0].caller.role == "teller"


async def test_in_memory_stores(teller: Caller) -> None:
    store = InMemoryConversationStore()
    audit = InMemoryAudit()
    conversation_id = await store.create(teller)
    await audit.record(teller, "question_asked", {})
    assert await store.recent_messages(conversation_id, 6) == []
    assert audit.names() == ["question_asked"]
