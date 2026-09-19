from pathlib import Path


def read_text(path):
    """Read the entire contents of a UTF-8 text file."""
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text, *, append=False):
    """Write text to a file.

    By default the file is overwritten. If append=True, the text is
    appended to the file instead. The file is created if it does not
    exist, but parent directories are not created automatically.
    """
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)
