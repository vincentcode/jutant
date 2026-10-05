"""Word documents. Headings become Markdown headings, so chunks keep their section titles;
tables become one line per row."""

from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

SUFFIXES = (".docx",)


def parse(path: Path) -> str:
    document: DocxDocument = docx.Document(str(path))
    blocks: list[str] = []
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if text:
                blocks.append(_heading(item, text))
        elif isinstance(item, Table):
            rows = [" | ".join(c.text.strip() for c in row.cells) for row in item.rows]
            blocks.append("\n".join(r for r in rows if r.strip(" |")))
    return "\n\n".join(b for b in blocks if b)


def _heading(paragraph: Paragraph, text: str) -> str:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return f"# {text}"
    if style.startswith("Heading "):
        level = style.removeprefix("Heading ")
        if level.isdigit():
            return f"{'#' * min(int(level), 6)} {text}"
    return text
