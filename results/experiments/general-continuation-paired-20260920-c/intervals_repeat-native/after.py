"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] with integers and start <= end, and returns a sorted list of
merged two-element lists. Overlapping intervals and intervals whose endpoints
touch are merged. Input lists are not mutated and no mutable sublists are
shared with the input.
"""


def merge_intervals(items):
    """Merge a list of [start, end] intervals.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists. Empty input returns [].
    """
    if not items:
        return []

    # Sort a copy of the intervals by start. We build new lists so we never
    # share mutable sublists with the input.
    sorted_intervals = sorted(([start, end] for start, end in items),
                              key=lambda interval: interval[0])

    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        # Overlap or touching endpoints (start <= last_end) merge together.
        if start <= last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
