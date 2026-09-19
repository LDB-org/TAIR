def read_bytes(path):
    """Read the entire contents of a binary file and return as bytes.

    Args:
        path: A str or Path-like object pointing to the file to read.

    Returns:
        The file contents as a bytes object.
    """
    with open(path, 'rb') as f:
        return f.read()


def write_bytes(path, data, *, append=False):
    """Write bytes to a binary file.

    Args:
        path: A str or Path-like object pointing to the file to write.
        data: The bytes to write.
        append: If True, append to the file instead of overwriting it.

    The file is opened in binary mode. By default the file is overwritten;
    when append=True, data is appended to the end of the file. Parent
    directories are not created.
    """
    mode = 'ab' if append else 'wb'
    with open(path, mode) as f:
        f.write(data)
