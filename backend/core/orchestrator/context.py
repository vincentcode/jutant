"""Builds the messages sent to the model: prompts, a few recent turns, then the question.

History is capped because a small model on CPU slows down sharply as the prompt grows.
"""

from core.types import Feature, Message


def build_messages(
    system_prompt: str, feature: Feature, history: list[Message], question: str
) -> list[Message]:
    """Pack `system.md` + feature prompt, then recent history, then the question."""
    raise NotImplementedError
