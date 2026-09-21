def chunks(values, size):
    """Split values into consecutive chunks of length size.

    Args:
        values: A list of items.
        size: The desired length of each chunk (must be > 0).

    Returns:
        A fresh list of fresh lists, each containing up to `size` items in
        original order. The last nonempty chunk is padded with None so that
        it has exactly `size` elements. Returns [] for empty values.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be > 0")

    if not values:
        return []

    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        if len(chunk) < size:
            chunk.extend([None] * (size - len(chunk)))
        result.append(chunk)
    return result
