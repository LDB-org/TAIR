from pathlib import Path


def read_text(path):
    """Read and return all UTF-8 text from the file at path."""
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text, append=False):
    """Write text as UTF-8 to the file at path.

    Overwrites by default, or appends when append=True.
    """
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)
