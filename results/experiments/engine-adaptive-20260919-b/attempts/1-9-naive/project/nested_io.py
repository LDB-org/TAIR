from pathlib import Path


def read_text(path):
    """Read the entire contents of a file as UTF-8 text.

    Args:
        path: A str or Path to the file to read.

    Returns:
        The file contents as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text, *, append=False):
    """Write text to a file as UTF-8, creating parent directories as needed.

    Args:
        path: A str or Path to the file to write.
        text: The text to write.
        append: If True, append to the file instead of overwriting.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)
