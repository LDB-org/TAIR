def chunks(values, size):
    """Split values into consecutive chunks of exactly `size` elements.

    Each chunk is a fresh list, and the returned outer list is fresh too.
    The last nonempty chunk is padded with None until it has exactly `size`
    elements. The input `values` is not mutated.

    Returns [] for empty values.

    Raises ValueError if size <= 0, even when values is empty.
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
