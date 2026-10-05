"""Splits document text into search-sized chunks. Pure functions.

Each chunk keeps its section heading so search results can cite the section. Text is split on
headings first, then paragraphs; a paragraph longer than a chunk is split by words. Tokens are
approximated as words / 0.75, which is close enough for English prose.
"""

import re
from dataclasses import dataclass

WORDS_PER_TOKEN = 0.75
# "# Title", "## 4.2 Joint accounts", or a short numbered line such as "4.2 Joint accounts".
# A numbered line containing a full stop is treated as a list item, not a heading.
HEADING = re.compile(r"^(#{1,6}\s+.+|\d+(\.\d+)*\.?\s+[A-Z][^.]{0,80})$")


@dataclass(frozen=True)
class Chunk:
    order: int
    section: str  # heading kept for citation
    text: str


def split(text: str, max_tokens: int = 350, overlap: int = 40) -> list[Chunk]:
    max_words = max(1, int(max_tokens * WORDS_PER_TOKEN))
    overlap_words = min(int(overlap * WORDS_PER_TOKEN), max_words // 2)
    chunks: list[Chunk] = []
    for section, body in _sections(text):
        for piece in _pack(_paragraphs(body), max_words, overlap_words):
            chunks.append(Chunk(len(chunks), section, piece))
    return chunks


def _sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        stripped = line.strip()
        if HEADING.match(stripped):
            sections.append((stripped.lstrip("#").strip(), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines)) for heading, lines in sections if "".join(lines).strip()]


def _paragraphs(body: str) -> list[list[str]]:
    return [p.split() for p in re.split(r"\n\s*\n", body) if p.strip()]


def _pack(paragraphs: list[list[str]], max_words: int, overlap_words: int) -> list[str]:
    """Fill chunks with whole paragraphs; split a paragraph only when it alone is too long.

    Consecutive chunks share the last `overlap_words` words, so a sentence cut at a boundary
    still appears whole in one of them.
    """
    pieces: list[str] = []
    current: list[str] = []
    for words in paragraphs:
        if current and len(current) + len(words) > max_words:
            pieces.append(" ".join(current))
            current = current[-overlap_words:] if overlap_words else []
        current = current + words
        while len(current) > max_words:
            pieces.append(" ".join(current[:max_words]))
            current = current[max_words - overlap_words :]
    if current and (not pieces or len(current) > overlap_words):
        pieces.append(" ".join(current))
    return pieces
