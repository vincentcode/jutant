"""Builds the messages sent to the model: prompts, a few recent turns, then the question.

History is capped because a small model on CPU slows down sharply as the prompt grows.
"""

from core.types import Feature, Message


def build_messages(
    system_prompt: str, feature: Feature, history: list[Message], question: str
) -> list[Message]:
    """The pack's shared system prompt and the feature prompt, recent turns, then the question.

    Only user and assistant text from history is kept; earlier tool calls and their results
    are left out, since each answer should come from fresh tool results.
    """
    system = "\n\n".join(p.strip() for p in (system_prompt, feature.prompt) if p.strip())
    turns = [
        Message(m.role, m.content)
        for m in history
        if m.role in ("user", "assistant") and m.content and not m.tool_calls
    ]
    return [Message("system", system), *turns, Message("user", question)]
