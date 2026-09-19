"""Small standard-library-only binary file I/O helpers."""

from pathlib import Path


def read_bytes(path) -> bytes:
    """Read the full contents of a file as bytes."""
    return Path(path).read_bytes()


def write_bytes(path, data, *, append=False) -> None:
    """Write bytes to a file.

    Creates a missing file. Overwrites by default, or appends when
    append=True. Does not create missing parent directories.
    """
    mode = "ab" if append else "wb"
    with open(path, mode) as f:
        f.write(data)
