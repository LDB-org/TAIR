def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Args:
        values: A list of items.
        size: An integer chunk size.

    Returns:
        A list of lists, each of length at most size, in original order.
        Returns [] for empty values.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    return [values[i:i + size] for i in range(0, len(values), size)]
