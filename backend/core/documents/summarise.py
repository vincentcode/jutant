"""Summarises a long document in parts: each chunk first, then the chunk summaries together.
A small model cannot read a whole long document at once."""

from core.documents.chunking import Chunk
from core.ports import ModelProvider
from core.types import Message

PART_PROMPT = "Summarise this part of a document in up to three sentences. Use only its text."
WHOLE_PROMPT = (
    "These are summaries of the parts of one document, in order. Write one summary of the whole "
    "document in up to five bullet points: its purpose, the key points and any effective date."
)


async def summarise(model: ModelProvider, chunks: list[Chunk]) -> str:
    if not chunks:
        return ""
    if len(chunks) == 1:
        return await _ask(model, WHOLE_PROMPT, chunks[0].text)
    parts = [await _ask(model, PART_PROMPT, _with_heading(chunk)) for chunk in chunks]
    return await _ask(model, WHOLE_PROMPT, "\n\n".join(parts))


def _with_heading(chunk: Chunk) -> str:
    return f"{chunk.section}\n{chunk.text}" if chunk.section else chunk.text


async def _ask(model: ModelProvider, instruction: str, text: str) -> str:
    reply = await model.chat([Message("system", instruction), Message("user", text)], [])
    return (reply.text or "").strip()
