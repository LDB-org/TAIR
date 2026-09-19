from pathlib import Path


def read_text(path):
    """Read the entire file at `path` as UTF-8 text.

    Accepts a str or Path. Raises FileNotFoundError if the file does not
    exist.
    """
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text):
    """Write `text` to a new file at `path` as UTF-8.

    Accepts a str or Path. If the file already exists, raises
    FileExistsError and preserves every byte of the existing file. Never
    overwrites or appends. Does not create parent directories.
    """
    p = Path(path)
    with open(p, "x", encoding="utf-8") as f:
        f.write(text)
