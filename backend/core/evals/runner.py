"""Replays a pack's test questions through the orchestrator and scores the answers.

Run against the fake system adapters and the real model, so a change of model or prompt can be
compared with the last run. Each question is asked in a new conversation, as the role it names,
with no feature picked, so routing is part of what is measured.
"""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.errors import PolicyDenied
from core.evals.scoring import EvalQuestion, EvalReport, QuestionResult, score
from core.events import Completed, Failed, FeatureSelected, ToolFinished, ToolStarted
from core.packs.loader import Pack
from core.types import Caller

if TYPE_CHECKING:
    from core.orchestrator.orchestrator import Orchestrator

EVAL_CALLER_ID = "eval"


async def run(
    pack: Pack,
    orchestrator: "Orchestrator",
    only: set[str] | None = None,
    progress: Callable[[QuestionResult], None] | None = None,
    repeat: int = 1,
) -> EvalReport:
    """Ask every eval question (or those whose id or feature is in `only`) `repeat` times and
    score each answer. The model's answers vary between runs, so one pass can be luck."""
    report = EvalReport(model=getattr(orchestrator.model, "model", ""))
    for data in pack.eval_questions:
        question = EvalQuestion.from_dict(data)
        if only and question.id not in only and question.feature not in only:
            continue
        for attempt in range(1, repeat + 1):
            result = score(await ask(orchestrator, question))
            result.attempt = attempt
            report.add(result)
            if progress:
                progress(result)
    return report


async def ask(orchestrator: "Orchestrator", question: EvalQuestion) -> QuestionResult:
    caller = Caller(EVAL_CALLER_ID, question.role, "staff", question.attributes)
    conversation_id = await orchestrator.conversations.create(caller)
    result = QuestionResult(question)
    feature_tools: set[str] = set()
    data_reached_caller = False
    started = time.perf_counter()
    try:
        async for event in orchestrator.ask(caller, conversation_id, question.question):
            match event:
                case FeatureSelected(feature_id):
                    result.routed_to = feature_id
                    feature_tools = set(orchestrator.registry.get(feature_id).tools)
                case ToolStarted(call):
                    result.tools_called.append(call.name)
                case ToolFinished(tool_result) if tool_result.ok:
                    data_reached_caller = True
                case Completed(answer):
                    result.answer = answer.text
                    result.citations = len(answer.citations)
                case Failed(reason):
                    result.failed = reason
    except PolicyDenied:
        result.failed = "denied"
    result.seconds = time.perf_counter() - started

    # Refused: the feature asked about was not used, or it was used and none of its tools
    # returned data to this caller.
    target_tools = set(orchestrator.registry.get(question.feature).tools)
    used_target = result.routed_to == question.feature or bool(feature_tools & target_tools)
    result.refused = not used_target or not data_reached_caller
    return result
