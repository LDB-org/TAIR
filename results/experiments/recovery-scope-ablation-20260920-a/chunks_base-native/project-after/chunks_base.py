"""Utility for splitting a list into consecutive chunks."""


def chunks(values, size):
    """Return consecutive chunks of ``values`` as fresh lists in a fresh outer list.

    Args:
        values: A list of items to split.
        size: The maximum size of each chunk (a positive integer).

    Returns:
        A new list of new lists, each containing consecutive items from ``values``
        in their original order. The last chunk may be shorter than ``size``.

    Raises:
        ValueError: If ``size`` is not a positive integer (``size <= 0``).

    The input ``values`` is never mutated.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    return [values[i:i + size] for i in range(0, len(values), size)]
