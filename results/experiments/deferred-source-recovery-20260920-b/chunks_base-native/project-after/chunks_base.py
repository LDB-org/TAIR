def chunks(values, size):
    """Split values into consecutive chunks of length size.

    Args:
        values: A list of items.
        size: The maximum length of each chunk (must be > 0).

    Returns:
        A fresh list of fresh lists, each containing consecutive items from
        values in their original order. The last chunk may be shorter than
        size. Returns [] when values is empty.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be greater than 0")

    result = []
    for i in range(0, len(values), size):
        result.append(list(values[i:i + size]))
    return result
