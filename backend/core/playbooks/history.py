"""Playbook steps as a conversation keeps them.

A turn's steps are stored with its message as records, so the client can show them as steps
(the current one as a card, earlier ones as a line each) rather than as text. The model still
reads them as text in its history, so later turns know where the procedure is.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from core.events import PlaybookStepShown
from core.types import PlaybookStep


def to_record(shown: PlaybookStepShown) -> dict[str, Any]:
    step = shown.step
    return {
        "playbook_id": shown.playbook_id,
        "playbook_title": shown.playbook_title,
        "order": step.order,
        "title": step.title,
        "instruction": step.instruction,
        "expects": step.expects,
        "choices": list(step.choices),
        "answered": shown.answered,
    }


def from_record(record: Mapping[str, Any]) -> PlaybookStepShown:
    step = PlaybookStep(
        order=int(record["order"]),
        title=str(record["title"]),
        instruction=str(record["instruction"]),
        audience=(),
        expects=record.get("expects", "confirm"),
        choices=tuple(record.get("choices") or ()),
    )
    return PlaybookStepShown(
        str(record["playbook_id"]),
        step,
        str(record.get("playbook_title") or ""),
        record.get("answered"),
    )


def as_text(text: str, steps: Iterable[PlaybookStepShown]) -> str:
    """A message's text with its steps, as the model reads it in the history."""
    lines = [text] if text else []
    for shown in steps:
        line = f"Step {shown.step.order}: {shown.step.title}. {shown.step.instruction}"
        if shown.answered:
            line += f" Answered from the record: {shown.answered}."
        lines.append(line)
    return "\n\n".join(lines)
