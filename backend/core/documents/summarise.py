"""Summarises a long document in parts: each chunk first, then the chunk summaries together.
A small model cannot read a whole long document at once."""

from core.documents.chunking import Chunk
from core.ports import ModelProvider


async def summarise(model: ModelProvider, chunks: list[Chunk]) -> str:
    """Summarise each chunk, then summarise the summaries."""
    raise NotImplementedError
