"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] (integers, start <= end) and returns a sorted list of merged
two-element lists. Intervals that overlap or whose endpoints touch are merged.
"""


def merge_intervals(items):
    """Merge overlapping/touching intervals and return a sorted list.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists. The input list and its
        sublists are not mutated, and no mutable sublists are shared with the
        input. Empty input returns [].
    """
    if not items:
        return []

    # Work on a copy of the intervals so we never mutate the input.
    intervals = [list(interval) for interval in items]
    intervals.sort(key=lambda interval: interval[0])

    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        # Overlap or touching endpoints (current[0] <= last[1]).
        if current[0] <= last[1]:
            if current[1] > last[1]:
                last[1] = current[1]
        else:
            merged.append(current)

    return merged
