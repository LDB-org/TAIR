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

    Raises:
        ValueError: If an item is not a two-element list, or if start > end.
    """
    if not items:
        return []

    # Validate and copy each interval so we never mutate or share the input.
    intervals = []
    for item in items:
        if len(item) != 2:
            raise ValueError(f"Each interval must have exactly two elements: {item!r}")
        start, end = item
        if start > end:
            raise ValueError(f"Interval start must be <= end: {item!r}")
        intervals.append([start, end])

    # Sort by start, then by end for deterministic ordering.
    intervals.sort(key=lambda iv: (iv[0], iv[1]))

    merged = [intervals[0][:]]
    for start, end in intervals[1:]:
        last = merged[-1]
        # Merge if overlapping or endpoints touch (start <= last_end).
        if start <= last[1]:
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
