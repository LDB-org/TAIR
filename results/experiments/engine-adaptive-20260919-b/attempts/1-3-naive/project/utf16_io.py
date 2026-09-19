from pathlib import Path


def read_text(path):
    """Read the whole file as UTF-16 text."""
    return Path(path).read_text(encoding='utf-16')


def write_text(path, text, *, append=False):
    """Write text to a file as UTF-16.

    Overwrites by default; appends when append=True.
    Does not create parent directories.
    """
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-16') as f:
        f.write(text)
