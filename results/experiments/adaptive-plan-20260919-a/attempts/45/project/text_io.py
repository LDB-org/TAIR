import os
from pathlib import Path


def read_text(path):
    """Read the entire contents of a UTF-8 text file.

    Args:
        path: A str or Path to the file to read.

    Returns:
        The file contents as a str.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path, text, *, append=False):
    """Write UTF-8 text to a file.

    By default the file is overwritten. If append=True, the text is
    appended to the file. Missing parent directories are created
    automatically, including nested parents.

    Args:
        path: A str or Path to the file to write.
        text: The text to write.
        append: If True, append to the file instead of overwriting.
    """
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)
