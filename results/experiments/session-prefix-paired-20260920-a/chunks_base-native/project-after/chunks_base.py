"""Provide a chunks function that splits a list into consecutive chunks."""


def chunks(values, size):
    """Split values into consecutive chunks of length size.

    Args:
        values: A list of items to chunk.
        size: The maximum length of each chunk (positive integer).

    Returns:
        A fresh list of fresh lists, each containing consecutive items from
        values in their original order. The last chunk may be shorter than
        size. Returns an empty list when values is empty.

    Raises:
        ValueError: If size is <= 0.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    result = []
    for i in range(0, len(values), size):
        result.append(values[i:i + size])
    return result
