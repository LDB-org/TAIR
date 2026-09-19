def read_text(path):
    """Read the whole file as UTF-8 text."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(path, text, *, append=False):
    """Write text to a file as UTF-8.

    Overwrites by default, or appends when append=True.
    Creates missing files but does not create parent directories.
    """
    mode = 'a' if append else 'w'
    with open(path, mode, encoding='utf-8') as f:
        f.write(text)
