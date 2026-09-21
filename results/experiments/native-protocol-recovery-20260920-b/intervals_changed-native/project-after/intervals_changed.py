"""Merge strictly overlapping intervals.

merge_intervals(items) takes a list of two-element lists [start, end] with
integer values and start <= end. It returns a new sorted list of merged
two-element lists.

Rules:
- Only strictly overlapping intervals are merged. Intervals whose endpoints
  merely touch (e.g. [1, 2] and [2, 3]) remain separate.
- Zero-length intervals (start == end) are allowed.
- The input list is not mutated, and no mutable sublists are shared with it.
- Empty input returns [].
"""


def merge_intervals(items):
    """Return a sorted list of merged intervals from items.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists.
    """
    if not items:
        return []

    # Work on a sorted copy of the input so the original is never mutated.
    sorted_items = sorted(items, key=lambda interval: (interval[0], interval[1]))

    merged = []
    for interval in sorted_items:
        # Copy the interval so we never share a mutable sublist with the input.
        current = [interval[0], interval[1]]
        if not merged:
            merged.append(current)
            continue

        last = merged[-1]
        # Merge only when there is a strict overlap: the current start is
        # strictly less than the last end. Merely touching endpoints
        # (current[0] == last[1]) do not merge.
        if current[0] < last[1]:
            if current[1] > last[1]:
                last[1] = current[1]
        else:
            merged.append(current)

    return merged
