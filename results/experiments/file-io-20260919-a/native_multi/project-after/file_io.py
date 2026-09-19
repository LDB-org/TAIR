"""Small standard-library-only file I/O helpers."""

from pathlib import Path


def read_text(path) -> str:
    """Read the full contents of a file as UTF-8 text."""
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text, *, append=False) -> None:
    """Write text to a file as UTF-8, overwriting or appending."""
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8", newline="") as f:
        f.write(text)
