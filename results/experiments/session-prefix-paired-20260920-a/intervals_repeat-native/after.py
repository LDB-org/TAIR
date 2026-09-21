"""Merge overlapping intervals.

Provides merge_intervals(items) which takes a list of two-element lists
[start, end] with integers and start <= end, and returns a sorted list of
merged two-element lists. Overlapping intervals and intervals whose endpoints
touch are merged. Input lists are not mutated and no mutable sublists are
shared with the input.
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

    # Work on a sorted copy of the intervals so the input is not mutated.
    sorted_items = sorted(items, key=lambda interval: interval[0])

    merged = []
    current_start, current_end = sorted_items[0]

    for start, end in sorted_items[1:]:
        if start <= current_end:
            # Overlap or touching endpoints -> merge.
            if end > current_end:
                current_end = end
        else:
            merged.append([current_start, current_end])
            current_start, current_end = start, end

    merged.append([current_start, current_end])
    return merged
