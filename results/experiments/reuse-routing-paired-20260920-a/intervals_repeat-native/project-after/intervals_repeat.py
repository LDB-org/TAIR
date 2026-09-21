"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] with integers and start <= end, and returns a sorted list of
merged two-element lists. Overlapping intervals and intervals whose endpoints
touch are merged. The input list is not mutated and no mutable sublists are
shared with it.
"""


def merge_intervals(items):
    """Merge overlapping/touching intervals.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A sorted list of merged two-element lists. Empty input returns [].
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) so the input is not
    # mutated. Each interval is copied into a fresh list.
    sorted_intervals = sorted(([start, end] for start, end in items))

    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # Overlap or touching endpoints: extend the last merged interval.
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
