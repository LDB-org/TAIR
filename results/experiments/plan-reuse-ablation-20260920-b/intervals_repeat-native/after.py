"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] (integers, start <= end) and returns a sorted list of merged
two-element lists. Overlapping intervals and intervals whose endpoints touch
are merged together.
"""


def merge_intervals(items):
    """Merge a list of [start, end] intervals into a sorted, merged list.

    Args:
        items: A list of two-element lists [start, end] with integer values
            and start <= end.

    Returns:
        A new sorted list of merged two-element lists. The input list and its
        sublists are not mutated, and no mutable sublists are shared with the
        input. An empty input returns [].
    """
    if not items:
        return []

    # Work on a copy of the intervals so we never mutate the input list or
    # share mutable sublists with it.
    intervals = sorted(([start, end] for start, end in items))

    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        # Overlap or touching endpoints (start <= last_end) are merged.
        if start <= last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
