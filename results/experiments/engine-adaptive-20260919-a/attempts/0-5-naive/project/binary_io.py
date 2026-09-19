def read_bytes(path):
    """Read the entire file at `path` and return its contents as bytes.

    `path` may be a str or a pathlib.Path. The file is read in binary mode,
    so arbitrary bytes (including invalid UTF-8) are preserved exactly.

    Raises FileNotFoundError if the file does not exist.
    """
    with open(path, 'rb') as f:
        return f.read()


def write_bytes(path, data, *, append=False):
    """Write `data` (bytes) to the file at `path`.

    `path` may be a str or a pathlib.Path. The file is opened in binary mode.
    By default the file is overwritten; pass `append=True` to append instead.

    No parent directories are created automatically. If the parent directory
    does not exist, an OSError is raised.
    """
    mode = 'ab' if append else 'wb'
    with open(path, mode) as f:
        f.write(data)
