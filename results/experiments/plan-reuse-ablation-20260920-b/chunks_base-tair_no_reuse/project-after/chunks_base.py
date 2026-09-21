def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Args:
        values: A list of items.
        size: The maximum size of each chunk (positive integer).

    Returns:
        A list of lists, each a fresh list, in original order.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    return [values[i:i + size] for i in range(0, len(values), size)]
