from pathlib import Path


def parse(path: Path) -> list[str]:
    """Text per page; an empty string marks a page with no text layer (needs OCR)."""
    raise NotImplementedError
