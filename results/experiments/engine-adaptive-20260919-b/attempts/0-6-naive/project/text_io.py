from pathlib import Path


def read_text(path):
    """Read the entire file at `path` as UTF-8 text.

    Accepts a str or Path. Raises FileNotFoundError if the file does not exist.
    """
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text):
    """Write `text` to `path` as UTF-8, creating a new file.

    Accepts a str or Path. If the file already exists, raises FileExistsError
    and preserves every byte of the existing file. Never overwrites or appends.
    Does not create parent directories.
    """
    p = Path(path)
    if p.exists():
        raise FileExistsError(f"File already exists: {p}")
    p.write_text(text, encoding="utf-8")
