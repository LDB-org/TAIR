def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Args:
        values: A list of items.
        size: The size of each chunk (must be a positive integer).

    Returns:
        A new list of new lists, each containing consecutive elements of values.
        The last chunk may be shorter than size. Returns [] for empty values.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")
    return [values[i:i + size] for i in range(0, len(values), size)]
