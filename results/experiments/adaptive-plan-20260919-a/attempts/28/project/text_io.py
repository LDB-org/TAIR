"""Small standard-library-only file I/O helpers."""

from pathlib import Path


def read_text(path) -> str:
    """Read the full contents of a file as UTF-8 text."""
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text) -> None:
    """Write text to a new file as UTF-8.

    Creates a new file. Raises FileExistsError if the destination
    already exists, preserving all existing bytes. Never overwrites
    or appends. Does not create missing parent directories.
    """
    with open(path, "x", encoding="utf-8", newline="") as f:
        f.write(text)
