"""Choosing one option from a short list: by asking the model, or by keywords as a fallback.

Used to pick a feature for a question and a playbook for a problem. The model is asked for a
single id; its reply is accepted only if it is exactly one of the ids, give or take quotes,
punctuation and case. A small model often adds words, so keyword scoring is the fallback.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from core.errors import ModelUnavailable
from core.ports import ModelProvider
from core.types import Message

STOPWORDS = frozenset(
    (  # noqa: SIM905  (a word list reads better as one string)
        "a an and are as at be by can do does for from has have how i in is it its me my no not "
        "of on or our please should show tell that the their there this to was what when where "
        "which who why will with you your"
    ).split()
)


@dataclass(frozen=True)
class Option:
    id: str
    description: str


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(w) for w in words if len(w) > 2 and w not in STOPWORDS}


def _stem(word: str) -> str:
    """Crude plural folding so 'transfers' matches 'transfer'."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def parse_choice(reply: str | None, ids: Sequence[str]) -> str | None:
    """The id the model replied with, or None if the reply is not exactly one of `ids`."""
    if not reply:
        return None
    cleaned = reply.strip().strip("`'\".:; ").lower()  # quotes and punctuation, in any order
    for option_id in ids:
        if cleaned == option_id.lower():
            return option_id
    return None


def best_keyword_match(text: str, options: Sequence[Option]) -> str | None:
    """The option whose id and description share the most keywords with `text`, if any."""
    wanted = keywords(text)
    best_id, best_score = None, 0
    for option in options:
        score = len(wanted & keywords(f"{option.id.replace('_', ' ')} {option.description}"))
        if score > best_score:
            best_id, best_score = option.id, score
    return best_id


async def choose(
    model: ModelProvider, instruction: str, text: str, options: Sequence[Option]
) -> str | None:
    """Ask the model to pick one option for `text`; fall back to keywords; None if neither works."""
    if not options:
        return None
    if len(options) == 1:
        return options[0].id
    chosen = await ask_model(model, instruction, text, options)
    return chosen or best_keyword_match(text, options)


async def ask_model(
    model: ModelProvider, instruction: str, text: str, options: Sequence[Option]
) -> str | None:
    """The option the model picks, or None if it is unavailable or its reply is not an id."""
    listing = "\n".join(f"{o.id}: {o.description}" for o in options)
    messages = [
        Message("system", f"{instruction}\n\n{listing}\n\nReply with the id only."),
        Message("user", text),
    ]
    try:
        reply = await model.chat(messages, [])
    except ModelUnavailable:
        return None
    return parse_choice(reply.text, [o.id for o in options])
