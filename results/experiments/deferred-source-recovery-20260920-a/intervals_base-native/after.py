"""Interval merging utilities."""

from __future__ import annotations


def merge_intervals(items):
    """Merge a list of [start, end] intervals.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists. Overlapping intervals
        and intervals whose endpoints touch are merged. The input list and its
        sublists are not mutated, and no mutable sublists are shared with the
        input.

    Examples:
        >>> merge_intervals([])
        []
        >>> merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]])
        [[1, 6], [8, 10], [15, 18]]
        >>> merge_intervals([[1, 4], [4, 5]])
        [[1, 5]]
    """
    if not items:
        return []

    # Work on a copy of the input so we never mutate the caller's list.
    sorted_items = sorted(([start, end] for start, end in items), key=lambda x: x[0])

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        # Merge if the current interval overlaps or touches the last merged one.
        if start <= last[1]:
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
