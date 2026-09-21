"""Merge strictly overlapping intervals."""


def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    Only strictly overlapping intervals are merged; intervals whose
    endpoints merely touch (e.g. [1, 2] and [2, 3]) remain separate.
    Zero-length intervals are allowed. The input list and its sublists
    are not mutated, and no mutable sublists are shared with the input.
    Empty input returns [].
    """
    if not items:
        return []

    # Work on copies so we never mutate or share sublists with the input.
    intervals = sorted(([start, end] for start, end in items))

    merged = [intervals[0][:]]
    for start, end in intervals[1:]:
        prev = merged[-1]
        # Strict overlap: current start must be strictly less than prev end.
        if start < prev[1]:
            if end > prev[1]:
                prev[1] = end
        else:
            merged.append([start, end])

    return merged
