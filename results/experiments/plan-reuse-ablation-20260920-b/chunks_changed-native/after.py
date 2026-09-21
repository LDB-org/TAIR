"""Provide a chunks() helper that splits a list into consecutive chunks."""

from __future__ import annotations

from typing import List, Optional, TypeVar

T = TypeVar("T")


def chunks(values: List[T], size: int) -> List[List[Optional[T]]]:
    """Split ``values`` into consecutive chunks of length ``size``.

    Each chunk is a fresh list, and the returned outer list is also fresh.
    The original ``values`` list is not mutated. The last nonempty chunk is
    padded with ``None`` until it has exactly ``size`` elements.

    Args:
        values: The list to split.
        size: The desired length of each chunk.

    Returns:
        A new list of new lists, in original order.

    Raises:
        ValueError: If ``size`` is <= 0, even when ``values`` is empty.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    if not values:
        return []

    result: List[List[Optional[T]]] = []
    for i in range(0, len(values), size):
        chunk = list(values[i : i + size])
        if len(chunk) < size:
            chunk.extend([None] * (size - len(chunk)))
        result.append(chunk)
    return result
