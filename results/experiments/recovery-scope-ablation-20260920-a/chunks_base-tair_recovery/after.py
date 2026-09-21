def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Args:
        values: A list of items.
        size: The maximum size of each chunk.

    Returns:
        A list of lists, each containing up to `size` consecutive items from
        `values`, in original order. The last chunk may be shorter than `size`.
        Returns an empty list for empty `values`.

    Raises:
        ValueError: If `size` is <= 0.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    return [values[i:i + size] for i in range(0, len(values), size)]
