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

    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        # Merge only when there is a strict overlap: the current start
        # is strictly less than the previous end. Touching endpoints
        # (start == last_end) are not merged.
        if start < last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
