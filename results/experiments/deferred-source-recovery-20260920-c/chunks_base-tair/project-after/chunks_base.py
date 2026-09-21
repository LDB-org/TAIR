def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    Input values is a list and size is an integer. The chunks are returned in
    original order and the input list is not mutated. Empty values returns [].
    A size <= 0 raises ValueError, even when values is empty. The last chunk
    may be shorter than size; no padding is added.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    return [values[i:i + size] for i in range(0, len(values), size)]
