"""Summarises a document in as few model calls as its length allows.

A document that fits in one part (about 2,500 tokens, well inside the model's context with
the prompt) is summarised in one call. A longer one is cut into parts at section boundaries
where it can be; each part is summarised, then the part summaries together. Every model call
costs about 30 seconds on a CPU, so the parts are as large as the context comfortably allows.
"""

from core.documents.chunking import WORDS_PER_TOKEN, Chunk, split
from core.ports import ModelProvider
from core.types import Message

PART_TOKENS = 2500
PART_PROMPT = "Summarise this part of a document in up to three sentences. Use only its text."
WHOLE_PROMPT = (
    "Summarise this document in up to five bullet points: its purpose, the key points and any "
    "effective date. Use only its text."
)
COMBINE_PROMPT = (
    "These are summaries of the parts of one document, in order. Write one summary of the whole "
    "document in up to five bullet points: its purpose, the key points and any effective date."
)


async def summarise(model: ModelProvider, text: str) -> str:
    parts = split_into_parts(text)
    if not parts:
        return ""
    if len(parts) == 1:
        return await _ask(model, WHOLE_PROMPT, parts[0])
    summaries = [await _ask(model, PART_PROMPT, part) for part in parts]
    return await _ask(model, COMBINE_PROMPT, "\n\n".join(summaries))


def split_into_parts(text: str, part_tokens: int = PART_TOKENS) -> list[str]:
    """The text in parts of up to `part_tokens`, each made of whole sections where possible."""
    budget = int(part_tokens * WORDS_PER_TOKEN)
    parts: list[str] = []
    current: list[str] = []
    words = 0
    for chunk in split(text, max_tokens=part_tokens, overlap=0):
        piece = _with_heading(chunk)
        size = len(piece.split())
        if current and words + size > budget:
            parts.append("\n\n".join(current))
            current, words = [], 0
        current.append(piece)
        words += size
    if current:
        parts.append("\n\n".join(current))
    return parts


def _with_heading(chunk: Chunk) -> str:
    return f"{chunk.section}\n{chunk.text}" if chunk.section else chunk.text


async def _ask(model: ModelProvider, instruction: str, text: str) -> str:
    reply = await model.chat([Message("system", instruction), Message("user", text)], [])
    return (reply.text or "").strip()
