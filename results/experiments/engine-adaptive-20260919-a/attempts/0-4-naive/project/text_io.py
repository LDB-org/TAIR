from pathlib import Path


def read_text(path):
    """Read the entire file at path as UTF-8 text."""
    return Path(path).read_text(encoding='utf-8')


def write_text(path, text, *, append=False):
    """Write text to path as UTF-8.

    Overwrites by default, or appends when append=True.
    Creates the file if missing, but does not create parent directories.
    """
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-8') as f:
        f.write(text)
