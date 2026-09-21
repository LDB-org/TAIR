def chunks(values, size):
    """Split values into consecutive chunks of length size.

    Args:
        values: A list of items.
        size: An integer chunk size.

    Returns:
        A fresh list of fresh lists, each containing up to `size` items in
        original order. The last nonempty chunk is padded with None until it
        has exactly `size` elements. Returns [] for empty values.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        while len(chunk) < size:
            chunk.append(None)
        result.append(chunk)
    return result
