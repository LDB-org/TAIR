"""Merge strictly overlapping intervals."""


def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    Only strictly overlapping intervals are merged; intervals whose
    endpoints merely touch (e.g. [1, 2] and [2, 3]) remain separate.
    Zero-length intervals are allowed. The input list is not mutated and
    no mutable sublists are shared with it. Empty input returns [].
    """
    if not items:
        return []

    # Work on a sorted copy of the input so the original is not mutated.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        prev_start, prev_end = merged[-1]
        # Merge when the intervals overlap in more than a single shared
        # endpoint. This is a strict overlap (start < prev_end), or a
        # containment case where one interval is zero-length at the shared
        # point (start == prev_end and one of them is zero-length).
        # Intervals that merely touch at an endpoint (start == prev_end with
        # both having positive length) remain separate.
        if start < prev_end or (
            start == prev_end and (prev_start == prev_end or start == end)
        ):
            merged[-1] = [prev_start, max(prev_end, end)]
        else:
            merged.append([start, end])

    return merged
