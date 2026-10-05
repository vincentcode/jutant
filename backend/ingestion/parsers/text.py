"""Plain text and Markdown: read as they are. Markdown headings become chunk sections."""

from pathlib import Path

SUFFIXES = (".txt", ".md")


def parse(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
