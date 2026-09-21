def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    Only strictly overlapping intervals are merged; intervals whose
    endpoints merely touch (e.g. [1,2] and [2,3]) remain separate.
    Zero-length intervals are allowed.

    The input list is not mutated and no mutable sublists are shared
    with it.
    """
    if not items:
        return []

    # Work on a copy of the input so we never mutate the caller's list.
    intervals = sorted(([start, end] for start, end in items))

    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        # Strict overlap: the current interval starts before the last
        # one ends. If start == last_end, they merely touch and must
        # remain separate.
        if start < last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
