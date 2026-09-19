from pathlib import Path


def read_text(path):
    """Read the entire file at `path` as UTF-8 text.

    Args:
        path: A str or Path to the file to read.

    Returns:
        The full contents of the file as a str.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text, *, append=False):
    """Write `text` to `path` as UTF-8, creating parent directories as needed.

    Args:
        path: A str or Path to the file to write.
        text: The text to write.
        append: If True, append to the file; otherwise overwrite it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as f:
        f.write(text)
