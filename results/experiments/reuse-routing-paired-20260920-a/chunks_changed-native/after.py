def chunks(values, size):
    """Split values into consecutive chunks of exactly size elements.

    Args:
        values: A list of items to chunk.
        size: The number of elements per chunk (must be > 0).

    Returns:
        A fresh list of fresh lists, each containing exactly `size` elements.
        The last chunk is padded with None to reach `size` elements.
        Returns [] when values is empty.

    Raises:
        ValueError: If size <= 0.
    """
    if size <= 0:
        raise ValueError("size must be greater than 0")

    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        while len(chunk) < size:
            chunk.append(None)
        result.append(chunk)
    return result
