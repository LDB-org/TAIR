from pathlib import Path


def read_text(path):
    """Read text from a file using UTF-16 encoding."""
    return Path(path).read_text(encoding='utf-16')


def write_text(path, text, *, append=False):
    """Write text to a file using UTF-16 encoding.

    If append is True, the text is appended to the file; otherwise the
    file is overwritten. Parent directories are not created.
    """
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-16') as f:
        f.write(text)
