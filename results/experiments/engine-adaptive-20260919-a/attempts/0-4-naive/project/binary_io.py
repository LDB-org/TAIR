from pathlib import Path


def read_bytes(path):
    """Read the entire file at path as raw bytes."""
    return Path(path).read_bytes()


def write_bytes(path, data, *, append=False):
    """Write raw bytes to path.

    Overwrites by default, or appends when append=True.
    Creates the file if missing, but does not create parent directories.
    """
    mode = 'ab' if append else 'wb'
    with open(path, mode) as f:
        f.write(data)
