def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Chunks are returned in original order. The input list is not mutated.
    Empty values returns []. A size <= 0 raises ValueError, including for
    empty values. The last nonempty chunk is padded with None until it has
    exactly size elements.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    result = []
    for i in range(0, len(values), size):
        chunk = values[i:i + size]
        if len(chunk) < size:
            chunk = chunk + [None] * (size - len(chunk))
        result.append(chunk)
    return result
