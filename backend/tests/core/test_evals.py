"""The eval runner and its scoring, on the scripted model."""

from types import SimpleNamespace

from core.evals.runner import run
from core.evals.scoring import EvalQuestion, QuestionResult, score
from core.types import ModelReply, ToolCall
from providers.llm.fake import FakeModel
from tests.builders import doc_result, make_rig, record_result


def pack(*questions: dict) -> SimpleNamespace:
    return SimpleNamespace(eval_questions=questions)


POLICY_Q = {
    "id": "q1",
    "feature": "policy_qa",
    "role": "teller",
    "question": "KYC for joint accounts?",
    "expect_tool": "documents.search",
    "expect_contains": ["Proof of address"],
    "expect_citation": True,
}


async def test_a_correct_answer_passes_every_check() -> None:
    model = FakeModel(
        replies=[
            ModelReply("policy_qa"),
            ModelReply(None, (ToolCall("1", "documents.search", {"query": "joint"}),)),
            ModelReply("Each holder needs photo ID and proof of address."),
        ]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    report = await run(pack(POLICY_Q), rig.orchestrator)

    [result] = report.results
    assert result.checks == {
        "routed": True,
        "answered": True,
        "tool": True,
        "contains": True,
        "cited": True,
    }
    assert report.passed == 1
    assert report.features["policy_qa"].checks["contains"] == [1, 1]


async def test_misrouting_and_a_missing_fact_are_reported() -> None:
    model = FakeModel(
        replies=[
            ModelReply("transaction_lookup"),
            ModelReply("I am not sure."),
            ModelReply("Still not sure."),
        ]
    )
    rig = await make_rig(model)

    [result] = (await run(pack(POLICY_Q), rig.orchestrator)).results

    assert not result.passed
    assert result.checks["routed"] is False
    assert result.checks["contains"] is False
    assert result.routed_to == "transaction_lookup"


async def test_a_restricted_feature_counts_as_refused() -> None:
    question = {
        "id": "q2",
        "feature": "customer_360",
        "role": "teller",
        "question": "Summary of C1001",
        "expect_denied": True,
    }
    # customer_360 is not offered to a teller, so the router picks something else.
    model = FakeModel(
        replies=[ModelReply("policy_qa"), ModelReply("I cannot help."), ModelReply("No.")]
    )
    rig = await make_rig(model)
    [result] = (await run(pack(question), rig.orchestrator)).results
    assert result.checks == {"refused": True}


async def test_a_denied_tool_call_counts_as_refused() -> None:
    question = {
        "id": "q3",
        "feature": "transaction_lookup",
        "role": "teller",
        "question": "Status of TX-1",
        "expect_denied": True,
    }
    from core.types import ToolResult

    model = FakeModel(
        replies=[
            ModelReply("transaction_lookup"),
            ModelReply(None, (ToolCall("1", "transactions.get_status", {"query": "TX-1"}),)),
            ModelReply("Not available."),
        ]
    )
    rig = await make_rig(
        model, results={"transactions.get_status": ToolResult("", ok=False, error="denied")}
    )
    [result] = (await run(pack(question), rig.orchestrator)).results
    assert result.passed


async def test_data_reaching_a_caller_who_should_be_refused_fails() -> None:
    question = EvalQuestion.from_dict(
        {
            "id": "q4",
            "feature": "transaction_lookup",
            "role": "teller",
            "question": "x",
            "expect_denied": True,
        }
    )
    leaked = QuestionResult(question, routed_to="transaction_lookup", refused=False)
    assert not score(leaked).passed


async def test_only_selects_questions_by_id_or_feature() -> None:
    other = {**POLICY_Q, "id": "q9", "feature": "transaction_lookup", "expect_tool": None}
    model = FakeModel(
        replies=[ModelReply("transaction_lookup"), ModelReply("Fine."), ModelReply("Fine.")]
    )
    rig = await make_rig(model, results={"transactions.get_status": record_result("T", "1", {})})
    report = await run(pack(POLICY_Q, other), rig.orchestrator, only={"transaction_lookup"})
    assert [r.question.id for r in report.results] == ["q9"]


async def test_repeated_runs_show_a_question_that_passes_only_sometimes() -> None:
    search = ModelReply(None, (ToolCall("1", "documents.search", {"query": "joint"}),))
    model = FakeModel(
        replies=[
            ModelReply("policy_qa"),
            search,
            ModelReply("Photo ID and proof of address."),
            ModelReply("policy_qa"),
            search,
            ModelReply("Photo ID only."),  # misses the fact
        ]
    )
    rig = await make_rig(model, results={"documents.search": doc_result("KYC Policy", "4.2")})

    report = await run(pack(POLICY_Q), rig.orchestrator, repeat=2)

    assert [(r.question.id, r.attempt, r.passed) for r in report.results] == [
        ("q1", 1, True),
        ("q1", 2, False),
    ]
    assert report.unstable == ["q1"]
    assert report.as_dict()["unstable"] == ["q1"]
