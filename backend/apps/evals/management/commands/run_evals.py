"""Run the pack's eval questions against the real model and the configured MCP servers.

    python manage.py run_evals                         # every question
    python manage.py run_evals --only policy_qa,q03    # some features or question ids
    python manage.py run_evals --model qwen2.5:14b     # compare another model
    python manage.py run_evals --repeat 3                # each question three times
    python manage.py run_evals --output report.json

Use the fake system adapters (JUTANT_BANKING_ADAPTERS=fake), so answers can be checked against
known data. Each question is asked in a new conversation under the staff id "eval".
"""

import asyncio
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.test.utils import override_settings

from config.container import build_runtime
from core.evals.runner import run
from core.evals.scoring import EvalReport, QuestionResult


class Command(BaseCommand):
    help = "Run the pack's eval questions against the real model and report per feature."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--only", default="", help="comma-separated question ids or features")
        parser.add_argument("--model", default="", help="the chat model to use instead")
        parser.add_argument("--output", type=Path, default=Path("evals-report.json"))
        parser.add_argument("--repeat", type=int, default=1, help="ask each question N times")

    def handle(self, *args, **options) -> None:
        only = {item.strip() for item in options["only"].split(",") if item.strip()} or None
        model = options["model"] or settings.JUTANT_LLM_MODEL
        with override_settings(JUTANT_LLM_MODEL=model):
            report = asyncio.run(self._run(only, max(1, options["repeat"])))
        options["output"].write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
        self._summary(report)
        self.stdout.write(f"Report written to {options['output']}")

    async def _run(self, only: set[str] | None, repeat: int) -> EvalReport:
        runtime = build_runtime()
        await runtime.start()
        try:
            return await run(runtime.pack, runtime.orchestrator, only, self._progress, repeat)
        finally:
            await runtime.stop()

    def _progress(self, result: QuestionResult) -> None:
        mark = "PASS" if result.passed else "FAIL"
        failed = [name for name, ok in result.checks.items() if not ok]
        detail = f"  failed: {', '.join(failed)}" if failed else ""
        self.stdout.write(
            f"{mark} {result.question.id:<5}#{result.attempt} {result.question.feature:<28} "
            f"{result.seconds:5.0f}s{detail}"
        )
        if not result.passed:  # enough to see why without opening the report
            answer = " ".join(result.answer.split())[:160]
            self.stdout.write(
                f"      routed {result.routed_to}, tools {result.tools_called or 'none'}, "
                f"failed {result.failed or '-'}: {answer!r}"
            )
        self.stdout.flush()

    def _summary(self, report: EvalReport) -> None:
        self.stdout.write(
            f"\nModel {report.model}: {report.passed} of {len(report.results)} passed, "
            f"median {report.median_seconds:.0f}s per question"
        )
        if report.unstable:
            self.stdout.write(f"  passed only sometimes: {', '.join(report.unstable)}")
        for feature in report.features.values():
            checks = "  ".join(
                f"{name} {ok}/{total}" for name, (ok, total) in feature.checks.items()
            )
            self.stdout.write(
                f"  {feature.feature_id:<28} {feature.passed}/{feature.total}  {checks}"
            )
