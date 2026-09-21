def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Only strictly overlapping intervals are merged; intervals whose
    endpoints merely touch (e.g. [1,2] and [2,3]) remain separate.
    Zero-length intervals are allowed. Input lists are not mutated and
    no mutable sublists are shared with the input.
    """
    if not items:
        return []

    # Work on copies so we never mutate the input or share sublists.
    sorted_items = sorted(([start, end] for start, end in items))

    result = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last_start, last_end = result[-1]
        # Merge only when strictly overlapping: start < last_end.
        # Touching endpoints (start == last_end) stay separate.
        if start < last_end:
            if end > last_end:
                result[-1][1] = end
        else:
            result.append([start, end])

    return result
