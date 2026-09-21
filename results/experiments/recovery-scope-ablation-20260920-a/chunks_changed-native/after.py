def chunks(values, size):
    """Split values into consecutive chunks of length size.

    Args:
        values: A list of items.
        size: The desired size of each chunk (must be a positive integer).

    Returns:
        A fresh list of fresh lists, each containing up to `size` consecutive
        items from `values` in their original order. The last nonempty chunk is
        padded with None so that it has exactly `size` elements.

    Raises:
        ValueError: If `size` is not a positive integer (<= 0).
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        if len(chunk) < size:
            chunk.extend([None] * (size - len(chunk)))
        result.append(chunk)
    return result
