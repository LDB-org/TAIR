def chunks(values, size):
    """Split values into consecutive chunks of length size.

    Args:
        values: A list of items.
        size: The desired size of each chunk (positive integer).

    Returns:
        A fresh list of fresh lists, each containing consecutive elements
        from values in original order. The last nonempty chunk is padded
        with None until it has exactly size elements.

    Raises:
        ValueError: If size <= 0, even when values is empty.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    if not values:
        return []

    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        if len(chunk) < size:
            chunk.extend([None] * (size - len(chunk)))
        result.append(chunk)
    return result
