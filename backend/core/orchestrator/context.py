"""Builds the messages sent to the model: prompts, a few recent turns, then the question.

History is capped because a small model on CPU slows down sharply as the prompt grows.
"""

from core.types import Feature, Message

# The platform's own rule, for every pack and feature: the assistant reads, it never acts. A
# small model otherwise offers "shall I proceed with the transfer?" after looking one up.
READ_ONLY = (
    "You cannot make changes, payments or transfers, or act on accounts or records, and never "
    "offer to. If asked to, say so, and say how staff can do it."
)


def build_messages(
    system_prompt: str, feature: Feature, history: list[Message], question: str
) -> list[Message]:
    """The pack's shared system prompt, the platform's rule and the feature prompt, recent
    turns, then the question.

    Only user and assistant text from history is kept; earlier tool calls and their results
    are left out, since each answer should come from fresh tool results.
    """
    parts = (system_prompt, READ_ONLY, feature.prompt)
    system = "\n\n".join(p.strip() for p in parts if p.strip())
    turns = [
        Message(m.role, m.content)
        for m in history
        if m.role in ("user", "assistant") and m.content and not m.tool_calls
    ]
    return [Message("system", system), *turns, Message("user", question)]
