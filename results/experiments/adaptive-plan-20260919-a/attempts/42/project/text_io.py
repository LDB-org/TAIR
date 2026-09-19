"""Small standard-library-only file I/O helpers using UTF-16."""

from pathlib import Path


def read_text(path) -> str:
    """Read the full contents of a file as UTF-16 text."""
    return Path(path).read_text(encoding="utf-16")


def write_text(path, text, *, append=False) -> None:
    """Write text to a file as UTF-16.

    Creates a missing file. Overwrites by default, or appends when
    append=True. Does not create missing parent directories.
    """
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-16", newline="") as f:
        f.write(text)
