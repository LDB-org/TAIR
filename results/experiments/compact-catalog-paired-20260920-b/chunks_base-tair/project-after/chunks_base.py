def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Chunks are returned in original order. The input list is not mutated.
    The last chunk may be shorter than size; no padding is added.
    Returns [] for empty values. Raises ValueError for size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    return [values[i:i + size] for i in range(0, len(values), size)]
