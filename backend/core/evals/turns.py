"""How well the assistant decides what a message is about, from the audit log: whether it asks
staff too often or too rarely.

Asking too often shows as the picker shown on many turns, staff mostly picking its first choice
(the most likely one, which the assistant would have chosen anyway), or ignoring it. Asking too
rarely (guessing wrong) shows as thumbs-down "wrong kind of help", the same message sent again
with something chosen, or a return to the earlier subject right after a new one began. These are
signals to look into, not scores: a labelled held-out run measures (`core.evals.labels`).

Reads audit records only (`question_asked`, `turn_read`, `feature_routed`, `clarify_shown`,
`feedback_given`), in the order they were written.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Decided by staff, not guessed: their reply_as, a locked feature, a pick, the first message.
STAFF = frozenset({"staff", "locked", "client", "first"})


@dataclass
class TurnReport:
    turns: int = 0  # messages staff sent (a pick's resend is not a new one)
    decided: Counter[str] = field(default_factory=Counter)  # what decided each read turn
    routed: Counter[str] = field(default_factory=Counter)  # what chose each new subject's feature
    asked: Counter[str] = field(default_factory=Counter)  # pickers shown, by reason
    picked: Counter[str] = field(default_factory=Counter)  # picks, by the kind picked
    picked_first: int = 0  # picks of the first (most likely) choice
    ignored: int = 0  # a picker answered by typing something else
    resent: int = 0  # the same message sent again with something chosen, without a picker
    quick_returns: int = 0  # back to the earlier subject right after a new one began
    thumbs_down: int = 0
    wrong_feature: int = 0  # thumbs-down "wrong kind of help"

    @property
    def asked_total(self) -> int:
        return sum(self.asked.values())

    @property
    def picks(self) -> int:
        return sum(self.picked.values())


def summarise(records: Iterable[tuple[str, str, Mapping[str, Any]]]) -> TurnReport:
    """`records`: (conversation id, event name, detail), oldest first."""
    report = TurnReport()
    last_text: dict[str, str] = {}  # conversation -> its previous message
    shown: dict[str, list[dict[str, Any]]] = {}  # conversation -> the open picker's choices
    last_read: dict[str, tuple[str, str]] = {}  # conversation -> previous (action, by)
    for conversation, name, detail in records:
        if name == "question_asked":
            text = str(detail.get("text") or "")
            picked = detail.get("picked")
            choices = shown.pop(conversation, None)
            if picked is not None and choices is not None and 0 <= picked < len(choices):
                report.picked[str(choices[picked].get("kind"))] += 1
                report.picked_first += picked == 0
                if text == last_text.get(conversation):
                    continue  # the message sent again with the pick: not a new one
                choices = None  # a new message with the kind of help picked
            report.turns += 1
            if choices is not None:
                report.ignored += 1
            elif text and text == last_text.get(conversation) and _chosen(detail):
                report.resent += 1
            last_text[conversation] = text
        elif name == "turn_read":
            action, by = str(detail.get("action")), str(detail.get("by"))
            report.decided[by] += 1
            before = last_read.get(conversation)
            if action == "return" and before and before[0] == "new" and before[1] not in STAFF:
                report.quick_returns += 1
            last_read[conversation] = (action, by)
        elif name == "feature_routed":
            report.routed[str(detail.get("chosen_by"))] += 1
        elif name == "clarify_shown":
            report.asked[str(detail.get("reason") or "unknown")] += 1
            shown[conversation] = list(detail.get("choices") or [])
        elif name == "feedback_given" and detail.get("rating") == "down":
            report.thumbs_down += 1
            report.wrong_feature += detail.get("reason") == "wrong_feature"
    return report


def _chosen(detail: Mapping[str, Any]) -> bool:
    """Sent saying what it is: a feature, or a reply_as other than a procedure's controls."""
    return bool(detail.get("feature_id")) or detail.get("reply_as") in ("question", "continue")


def render(report: TurnReport) -> str:
    """The report for a person to read."""
    turns = report.turns or 1
    picks = report.picks or 1
    asked = report.asked_total or 1
    lines = [
        f"Messages: {report.turns}",
        "",
        "Asking",
        f"  picker shown        {_of(report.asked_total, turns, 'messages')}",
    ]
    lines += [f"    {reason:<18}{n}" for reason, n in report.asked.most_common()]
    lines += [
        f"  picked              {_of(report.picks, asked, 'pickers')}",
        f"    first choice      {_of(report.picked_first, picks, 'picks')}",
    ]
    lines += [f"    {kind:<18}{n}" for kind, n in report.picked.most_common()]
    lines += [
        f"  ignored             {_of(report.ignored, asked, 'pickers')}",
        "",
        "Guessing",
        f"  sent again, chosen  {report.resent}",
        f"  quick returns       {report.quick_returns}",
        f"  thumbs-down         {report.thumbs_down}, wrong kind of help {report.wrong_feature}",
        "",
        "Read turns decided by",
    ]
    lines += [f"  {by:<20}{n}" for by, n in report.decided.most_common()]
    lines += ["", "New subjects' feature chosen by"]
    lines += [f"  {by:<20}{n}" for by, n in report.routed.most_common()]
    lines += [
        "",
        "Too often: many pickers, mostly the first choice picked, or pickers ignored.",
        "Too rarely: messages sent again with a choice, quick returns, wrong kind of help.",
    ]
    return "\n".join(lines)


def _of(part: int, whole: int, what: str) -> str:
    return f"{part} ({round(100 * part / whole)}% of {what})"
