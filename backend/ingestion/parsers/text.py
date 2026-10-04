from pathlib import Path


def parse(path: Path) -> str:
    return path.read_text(encoding="utf-8")
