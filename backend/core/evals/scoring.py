"""What an eval run measures, per question and per feature.

Each question is scored on the checks it asks for:

- routed: the router chose the expected feature (the question is asked with no feature picked);
- tool: the expected tool was called;
- contains: every expected phrase appears in the answer (ignoring case);
- cited: the answer has at least one source, when a citation is expected;
- refused: when the question should be refused, no data from the feature's tools reached the
  answer (the feature was not offered, or its tool call was denied).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    feature: str
    role: str
    question: str
    attributes: dict[str, Any] = field(default_factory=dict)
    expect_tool: str | None = None
    expect_contains: tuple[str, ...] = ()
    expect_citation: bool = False
    expect_denied: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalQuestion":
        return cls(
            id=str(data["id"]),
            feature=str(data["feature"]),
            role=str(data["role"]),
            question=str(data["question"]),
            attributes=dict(data.get("attributes") or {}),
            expect_tool=data.get("expect_tool"),
            expect_contains=tuple(data.get("expect_contains") or ()),
            expect_citation=bool(data.get("expect_citation")),
            expect_denied=bool(data.get("expect_denied")),
        )


@dataclass
class QuestionResult:
    question: EvalQuestion
    routed_to: str | None = None
    tools_called: list[str] = field(default_factory=list)
    answer: str = ""
    citations: int = 0
    failed: str | None = None  # the turn's failure reason, if it ended in one
    refused: bool = False  # the caller was kept from the feature's data
    seconds: float = 0.0
    checks: dict[str, bool] = field(default_factory=dict)
    attempt: int = 1  # with repeated runs, which run of the question this is

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


def score(result: QuestionResult) -> QuestionResult:
    q = result.question
    checks: dict[str, bool] = {}
    if q.expect_denied:
        checks["refused"] = result.refused
    else:
        checks["routed"] = result.routed_to == q.feature
        checks["answered"] = result.failed is None
        if q.expect_tool:
            checks["tool"] = q.expect_tool in result.tools_called
        if q.expect_contains:
            text = result.answer.lower()
            checks["contains"] = all(phrase.lower() in text for phrase in q.expect_contains)
        if q.expect_citation:
            checks["cited"] = result.citations > 0
    result.checks = checks
    return result


@dataclass
class FeatureScore:
    feature_id: str
    total: int = 0
    passed: int = 0
    checks: dict[str, list[int]] = field(default_factory=dict)  # check -> [passed, total]

    def add(self, result: QuestionResult) -> None:
        self.total += 1
        self.passed += result.passed
        for name, ok in result.checks.items():
            tally = self.checks.setdefault(name, [0, 0])
            tally[0] += ok
            tally[1] += 1


@dataclass
class EvalReport:
    model: str = ""
    results: list[QuestionResult] = field(default_factory=list)
    features: dict[str, FeatureScore] = field(default_factory=dict)

    def add(self, result: QuestionResult) -> None:
        self.results.append(result)
        feature = result.question.feature
        self.features.setdefault(feature, FeatureScore(feature)).add(result)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def unstable(self) -> list[str]:
        """Questions that passed on some runs and failed on others."""
        outcomes: dict[str, set[bool]] = {}
        for r in self.results:
            outcomes.setdefault(r.question.id, set()).add(r.passed)
        return [qid for qid, seen in outcomes.items() if len(seen) > 1]

    @property
    def median_seconds(self) -> float:
        times = sorted(r.seconds for r in self.results)
        return times[len(times) // 2] if times else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "passed": self.passed,
            "total": len(self.results),
            "unstable": self.unstable,
            "median_seconds": round(self.median_seconds, 1),
            "features": {
                f.feature_id: {"passed": f.passed, "total": f.total, "checks": f.checks}
                for f in self.features.values()
            },
            "questions": [
                {
                    "id": r.question.id,
                    "attempt": r.attempt,
                    "feature": r.question.feature,
                    "question": r.question.question,
                    "passed": r.passed,
                    "checks": r.checks,
                    "routed_to": r.routed_to,
                    "tools_called": r.tools_called,
                    "citations": r.citations,
                    "failed": r.failed,
                    "seconds": round(r.seconds, 1),
                    "answer": r.answer,
                }
                for r in self.results
            ],
        }
