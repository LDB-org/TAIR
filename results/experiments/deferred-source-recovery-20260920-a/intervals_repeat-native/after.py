"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] (integers, start <= end) and returns a sorted list of merged
two-element lists. Overlapping intervals and intervals whose endpoints touch
are merged together.
"""


def merge_intervals(items):
    """Merge overlapping/touching intervals.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists. The input list and its
        sublists are not mutated, and no mutable sublists are shared with the
        input.

    Raises:
        ValueError: If an interval is not a two-element list, contains
            non-integers, or has start > end.
    """
    if not items:
        return []

    # Validate and copy each interval so we never mutate or share sublists
    # with the caller.
    intervals = []
    for item in items:
        if len(item) != 2:
            raise ValueError("each interval must have exactly two elements")
        start, end = item
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("interval endpoints must be integers")
        if start > end:
            raise ValueError("interval start must be <= end")
        intervals.append([start, end])

    # Sort by start, then by end, for deterministic merging.
    intervals.sort(key=lambda iv: (iv[0], iv[1]))

    merged = [intervals[0][:]]
    for start, end in intervals[1:]:
        last = merged[-1]
        # Merge if overlapping or touching (start <= last_end).
        if start <= last[1]:
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
