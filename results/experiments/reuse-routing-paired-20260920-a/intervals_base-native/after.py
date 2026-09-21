"""Interval merging utilities."""


def merge_intervals(items):
    """Merge a list of [start, end] intervals.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists. Overlapping intervals
        and intervals whose endpoints touch are merged. Empty input returns [].

    The input list is not mutated, and no mutable sublists are shared with it.
    """
    if not items:
        return []

    # Work on a sorted copy of the intervals so the input is not mutated.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # Overlap or touching endpoints: merge into the last interval.
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
