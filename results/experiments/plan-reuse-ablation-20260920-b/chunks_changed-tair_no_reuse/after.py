def chunks(values, size):
    """Return consecutive chunks of values, each of length size.

    The last nonempty chunk is padded with None to exactly size elements.
    Returns a fresh outer list of fresh inner lists, without mutating values.
    Returns [] for empty values. Raises ValueError if size <= 0.
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
