"""Replay a held-out question set and write transcripts for a person to grade.

    python manage.py run_heldout --file heldout.md                       # every item, once
    python manage.py run_heldout --file heldout.md --repeat 3
    python manage.py run_heldout --file heldout.md --only ONE-002,EDGE-001 --role customer_service
    python manage.py run_heldout --file heldout.md --output heldout-report

Held-out questions are written by people, not by whoever builds the assistant, and are never
used for tuning: they measure, nothing is changed to make them pass. The file is YAML (it may
sit in a .md, and trailing prose after the YAML is ignored). Each item with an `id` and a
`message` or `messages` is a conversation: its staff messages are asked in order in one new
conversation. Assistant lines in an item are what its author expects to see; they are not
played. The caller is the file's `default_staff_context`, or the item's `staff`, or `--role`.

Answers are not scored automatically: an item's expected phrases are shown as hints next to
the answers (found or not), and the person grading judges by meaning. Writes <output>.json
(everything) and <output>.md (for reading).

Whether the assistant asks when it should is scored, for messages with a label:

    messages:
      - text: "Why did TX-0002 fail?"
        expect: transaction_lookup     # the feature that should answer
      - text: "and when does the money come back?"
        expect: transaction_lookup
        subject: same                  # optional: same (an open subject) or new
      - text: "what about the other one?"
        expect: ask                    # even a person could not tell: it should ask
        then: product_lookup           # optional: what staff would pick, to go on

When the assistant asks, the labelled choice is picked as staff would. A one-message item takes
its label from the item (`expect`, `subject`, `then`). See `core.evals.labels`.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml
from django.core.management.base import BaseCommand, CommandError, CommandParser

from config.container import build_runtime
from core.evals import labels as label_scoring
from core.evals.transcript import HELDOUT_CALLER_ID, Label, Transcript, replay
from core.types import Caller


class Command(BaseCommand):
    help = "Replay a held-out question set and write transcripts to grade."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--file", type=Path, required=True)
        parser.add_argument("--only", default="", help="comma-separated item ids")
        parser.add_argument("--repeat", type=int, default=1)
        parser.add_argument("--role", default="", help="ask as this role instead")
        parser.add_argument("--output", type=Path, default=Path("heldout-report"))

    def handle(self, *args, **options) -> None:
        data = read_set(options["file"])
        only = {i.strip() for i in options["only"].split(",") if i.strip()}
        items = [i for i in find_items(data) if not only or i["id"] in only]
        if not items:
            raise CommandError("no items found")
        default = data.get("default_staff_context") or {}
        transcripts = asyncio.run(
            self._run(items, default, options["role"], max(1, options["repeat"]))
        )
        out: Path = options["output"]
        report = [
            {"item": item, "attempts": [t.as_dict() for t in transcripts[item["id"]]]}
            for item in items
        ]
        asking = label_scoring.score(t for done in transcripts.values() for t in done)
        everything = {"asking": asking.as_dict(), "items": report}
        out.with_suffix(".json").write_text(json.dumps(everything, indent=2), encoding="utf-8")
        out.with_suffix(".md").write_text(markdown(report, asking), encoding="utf-8")
        self.stdout.write(f"Wrote {out.with_suffix('.md')} and {out.with_suffix('.json')}")

    async def _run(
        self, items: list[dict[str, Any]], default: dict[str, Any], role: str, repeat: int
    ) -> dict[str, list[Transcript]]:
        runtime = build_runtime()
        await runtime.start()
        try:
            done: dict[str, list[Transcript]] = {}
            for item in items:
                staff = {**default, **(item.get("staff") or {})}
                caller = Caller(
                    HELDOUT_CALLER_ID,
                    role or staff.get("role", "teller"),
                    "staff",
                    {"branch": staff.get("branch", "")},
                )
                for attempt in range(1, repeat + 1):
                    transcript = await replay(
                        runtime.orchestrator,
                        caller,
                        staff_messages(item),
                        item["id"],
                        attempt,
                        labels(item),
                    )
                    done.setdefault(item["id"], []).append(transcript)
                    seconds = sum(t.seconds for t in transcript.turns)
                    self.stdout.write(
                        f"{item['id']:<16}#{attempt} {caller.role:<17}{seconds:6.0f}s"
                    )
                    self.stdout.flush()
            return done
        finally:
            await runtime.stop()


def read_set(path: Path) -> dict[str, Any]:
    """The YAML at the top of the file, up to any trailing prose."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line[0].isspace() and not line.startswith("#") and lines:
            break  # the first unindented line after the top-level key: prose, not YAML
        lines.append(line)
    data = yaml.safe_load("\n".join(lines)) or {}
    return data.get("evaluation_set", data)


def find_items(node: Any) -> list[dict[str, Any]]:
    """Every mapping with an `id` and a `message` or `messages`, in file order."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "id" in node and ("message" in node or "messages" in node):
            return [node]
        for value in node.values():
            found += find_items(value)
    elif isinstance(node, list):
        for value in node:
            found += find_items(value)
    return found


def staff_messages(item: dict[str, Any]) -> list[str]:
    if "message" in item:
        return [str(item["message"])]
    said = []
    for message in item["messages"]:
        if isinstance(message, str):
            said.append(message)
        elif message.get("role", "staff") != "assistant":
            said.append(str(message["text"]))
    return said


def labels(item: dict[str, Any]) -> list[Label | None]:
    """Each staff message's label, if it has one (`expect`)."""

    def label(block: Any) -> Label | None:
        if not isinstance(block, dict) or not block.get("expect"):
            return None
        return Label(
            str(block["expect"]), str(block.get("subject") or ""), str(block.get("then") or "")
        )

    if "message" in item:
        return [label(item)]
    return [
        label(m)
        for m in item["messages"]
        if isinstance(m, str) or m.get("role", "staff") != "assistant"
    ]


def hints(item: dict[str, Any]) -> dict[int, list[str]]:
    """Expected phrases by staff-message index, where the item says which message they are for."""
    expected = item.get("expected") or {}
    count = len(staff_messages(item))
    types = [
        m.get("type")
        for m in item.get("messages", [])
        if isinstance(m, dict) and m.get("role") != "assistant"
    ]
    found: dict[int, list[str]] = {}

    def add(index: int, block: Any) -> None:
        if isinstance(block, dict) and 0 <= index < count:
            found.setdefault(index, []).extend(str(p) for p in block.get("answer_contains", []))

    add(count - 1, expected)
    add(count - 1, expected.get("final"))
    for key, block in expected.items():
        if key.startswith("message_") and key[8:].isdigit():
            add(int(key[8:]) - 1, block)
        elif key in types:
            add(types.index(key), block)
        elif key == "side_question" and "side_question" in types:
            add(types.index("side_question"), block)
    return found


def markdown(report: list[dict[str, Any]], asking: label_scoring.LabelScore) -> str:
    out = ["# Held-out transcripts", ""]
    if asking.clear or asking.unclear:
        out += label_scoring.render(asking)
    for entry in report:
        item = entry["item"]
        expected = hints(item)
        out += [f"## {item['id']}", ""]
        if item.get("expected"):
            out += [
                "Expected:",
                "",
                "```yaml",
                yaml.safe_dump(item["expected"], sort_keys=False).strip(),
                "```",
                "",
            ]
        for attempt in entry["attempts"]:
            out.append(
                f"**Attempt {attempt['attempt']}** · {attempt['role']} at {attempt['branch']}"
            )
            out.append("")
            for index, turn in enumerate(attempt["turns"]):
                route = turn["feature"] or "-"
                if turn["routed_by"]:
                    route += f" ({turn['routed_by']})"
                if turn["switched_from"]:
                    route += f", switched from {turn['switched_from']}"
                out.append(f"{index + 1}. **Staff:** {turn['message']}")
                out.append(f"   - Routed: {route}")
                if turn["reply_read_as"]:
                    out.append(f"   - Read as: {turn['reply_read_as']}")
                if turn["asked"]:
                    picked = f"; picked {turn['picked']}" if turn["picked"] else ""
                    out.append(
                        f"   - Asked ({turn['ask_reason']}): {'; '.join(turn['asked'])}{picked}"
                    )
                if turn["expect"]:
                    subject = f" ({turn['expect_subject']})" if turn["expect_subject"] else ""
                    out.append(f"   - Label: {turn['expect']}{subject}")
                for tool in turn["tools"]:
                    status = "ok" if tool.get("ok") else tool.get("error")
                    out.append(f"   - Tool: `{tool['name']}` {tool['arguments']} → {status}")
                for step in turn["steps"]:
                    out.append(f"   - Step shown: {step}")
                answer = " ".join(turn["answer"].split()) or "(none)"
                out.append(f"   - Answer: {answer}")
                if turn["sources"]:
                    out.append(f"   - Sources: {'; '.join(turn['sources'])}")
                if turn["failed"]:
                    out.append(f"   - Failed: {turn['failed']}")
                out.append(
                    f"   - Procedure after: {turn['procedure'] or 'none'} · {turn['seconds']}s"
                )
                for phrase in expected.get(index, []):
                    mark = "found" if phrase.lower() in turn["answer"].lower() else "not found"
                    out.append(f'   - Hint "{phrase}": {mark}')
            out.append("")
        out += ["Grade: _to be confirmed_", ""]
    return "\n".join(out)
