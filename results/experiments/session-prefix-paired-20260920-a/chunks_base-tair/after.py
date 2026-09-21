def chunks(values, size):
    """Return consecutive chunks of values as fresh lists in a fresh outer list.

    The input list is not mutated. An empty input returns []. A size <= 0
    raises ValueError, even for empty values. The last chunk may be shorter
    than size; no padding is added.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    result = []
    for i in range(0, len(values), size):
        result.append(list(values[i:i + size]))
    return result
