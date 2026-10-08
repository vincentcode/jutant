"""Scoring labelled transcripts: does the assistant ask when it should, and only then?

Each labelled message is either clear (a feature should answer it, maybe as the same subject or
a new one) or unclear (`ask`: even a person could not tell). Three numbers:

- asks too often: of the clear messages, how many it asked about;
- asks too rarely: of the unclear messages, how many it guessed instead of asking;
- right when it did not ask: of the clear messages it decided itself, how many it got right
  (the feature, and the subject when the label says).

Labels are written by people, never tuned to: they measure.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from core.evals.transcript import ASK, Transcript, Turn

SAME = frozenset({"continue", "return"})  # readings that keep to an open subject


@dataclass
class Miss:
    item_id: str
    attempt: int
    message: str
    expected: str
    got: str


@dataclass
class LabelScore:
    clear: int = 0
    asked_on_clear: int = 0
    decided_right: int = 0
    unclear: int = 0
    asked_on_unclear: int = 0
    misses: list[Miss] = field(default_factory=list)  # each wrong decision, to look into

    @property
    def decided(self) -> int:
        return self.clear - self.asked_on_clear

    def as_dict(self) -> dict[str, object]:
        return {
            "clear": self.clear,
            "asked_on_clear": self.asked_on_clear,
            "decided_right": self.decided_right,
            "unclear": self.unclear,
            "asked_on_unclear": self.asked_on_unclear,
            "misses": [vars(m) for m in self.misses],
        }


def score(transcripts: Iterable[Transcript]) -> LabelScore:
    result = LabelScore()
    for transcript in transcripts:
        for turn in transcript.turns:
            if turn.expect is None or turn.failed:
                continue
            got = _got(turn)
            if turn.expect == ASK:
                result.unclear += 1
                if turn.asked:
                    result.asked_on_unclear += 1
                else:
                    result.misses.append(_miss(transcript, turn, "ask", got))
                continue
            result.clear += 1
            if turn.asked:
                result.asked_on_clear += 1
                result.misses.append(_miss(transcript, turn, _wanted(turn), got))
            elif _right(turn):
                result.decided_right += 1
            else:
                result.misses.append(_miss(transcript, turn, _wanted(turn), got))
    return result


def _right(turn: Turn) -> bool:
    if turn.answered_by != turn.expect:
        return False
    if turn.expect_subject == "same":
        return turn.read_as in SAME
    if turn.expect_subject == "new":
        return turn.read_as == "new"
    return True


def _wanted(turn: Turn) -> str:
    return f"{turn.expect}{f' ({turn.expect_subject})' if turn.expect_subject else ''}"


def _got(turn: Turn) -> str:
    if turn.asked:
        return f"asked ({turn.ask_reason})"
    return f"{turn.answered_by or '-'} ({turn.read_as or '-'})"


def _miss(transcript: Transcript, turn: Turn, expected: str, got: str) -> Miss:
    return Miss(transcript.item_id, transcript.attempt, turn.message, expected, got)


def render(result: LabelScore) -> list[str]:
    """Markdown lines for the report."""
    return [
        "## Asking",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Asks too often (asked on a clear message) | "
        f"{_of(result.asked_on_clear, result.clear)} |",
        f"| Asks too rarely (guessed an unclear one) | "
        f"{_of(result.unclear - result.asked_on_unclear, result.unclear)} |",
        f"| Right when it decided itself | {_of(result.decided_right, result.decided)} |",
        "",
        *(
            [
                "Misses:",
                "",
                *(
                    f"- {m.item_id} #{m.attempt}: “{m.message}”: expected {m.expected}, got {m.got}"
                    for m in result.misses
                ),
                "",
            ]
            if result.misses
            else []
        ),
    ]


def _of(part: int, whole: int) -> str:
    return f"{part} of {whole} ({round(100 * part / whole)}%)" if whole else "none labelled"
