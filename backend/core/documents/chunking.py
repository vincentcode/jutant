"""Splits document text into search-sized chunks. Pure functions.

Each chunk keeps its section heading so search results can cite the section.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    order: int
    section: str  # heading kept for citation
    text: str


def split(text: str, max_tokens: int = 350, overlap: int = 40) -> list[Chunk]:
    """Split on headings first, then paragraphs."""
    raise NotImplementedError
