"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] (integers, start <= end) and returns a sorted list of merged
two-element lists. Overlapping intervals and intervals whose endpoints touch
are merged together.
"""


def merge_intervals(items):
    """Merge overlapping/touching intervals.

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

    # Work on a copy of the intervals so we never mutate the input.
    intervals = sorted(([start, end] for start, end in items))

    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        # Merge if overlapping or endpoints touch (start <= last_end).
        if start <= last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
