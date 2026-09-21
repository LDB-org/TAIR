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

    merged = [sorted_items[0][:]]
    for start, end in sorted_items[1:]:
        last_start, last_end = merged[-1]
        # Merge when the intervals strictly overlap (share an interior
        # region), or when they touch at a point where at least one of them
        # is zero-length (so the shared point is the whole of that interval).
        # Merely touching at a shared endpoint of two proper intervals does
        # not count as overlap and keeps them separate.
        if start < last_end or (
            start == last_end and (last_start == last_end or start == end)
        ):
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
