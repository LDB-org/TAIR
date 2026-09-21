def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Each chunk has exactly size elements; the last nonempty chunk is padded
    with None until it has exactly size elements. Returns [] for empty values.
    Raises ValueError for size <= 0, including when values is empty.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not values:
        return []
    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        while len(chunk) < size:
            chunk.append(None)
        result.append(chunk)
    return result
