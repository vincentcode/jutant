"""Follow-up questions: ones that lean on the conversation so far.

"TX-0002", "why did it fail?", "and for joint accounts?" mean little on their own. Routing
reads only the question, and the prefetch calls and document searches use only its words, so a
follow-up is given the previous turn's context, in code (no extra model call):

- routing prefers the feature that answered last, and leaves it only for a clear match elsewhere;
- prefetch calls and searches read the previous question too, after this one, so a reference
  or a document named there is found ("why did it fail?" after "status of TX-0002").

A question is a follow-up if it is short, opens as a continuation, or points back with a word
such as "it" or "those". The test is plain English, with no business vocabulary.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from core.types import Message

SHORT = 4  # words: "TX-0002", "and the savings one?"
OPENINGS = ("and ", "also ", "but ", "so ", "then ", "what about ", "how about ", "what if ")
POINTERS = frozenset({"it", "its", "that", "those", "these", "them", "they", "same"})


@dataclass(frozen=True)
class Previous:
    question: str | None = None  # staff's last question
    feature_id: str | None = None  # the feature that answered last


def is_follow_up(text: str) -> bool:
    words = re.findall(r"[a-z0-9'-]+", text.lower())
    if not words:
        return False
    return (
        len(words) <= SHORT or " ".join(words).startswith(OPENINGS) or bool(POINTERS & set(words))
    )


def previous(history: Sequence[Message]) -> Previous:
    question = next((m.content for m in reversed(history) if m.role == "user"), None)
    feature_id = next(
        (m.feature_id for m in reversed(history) if m.role == "assistant" and m.feature_id), None
    )
    return Previous(question, feature_id)


def lookup_text(text: str, before: Previous) -> str:
    """What prefetch calls and searches read: the question, then for a follow-up the previous
    question, so this question's own words still come first."""
    if before.question and is_follow_up(text):
        return f"{text}\n{before.question}"
    return text
