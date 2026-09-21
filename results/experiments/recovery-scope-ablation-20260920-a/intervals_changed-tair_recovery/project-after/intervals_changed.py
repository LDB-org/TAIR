def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Only strictly overlapping intervals are merged; intervals whose
    endpoints merely touch (e.g. [1,2] and [2,3]) remain separate.
    Zero-length intervals are allowed. The input is not mutated and no
    mutable sublists are shared with it.
    """
    if not items:
        return []

    # Sort a copy of the input by start, then end.
    sorted_items = sorted(items, key=lambda x: (x[0], x[1]))

    result = []
    for item in sorted_items:
        start, end = item[0], item[1]
        if not result:
            result.append([start, end])
            continue
        last = result[-1]
        # Strict overlap: current start must be strictly less than last end.
        # If start == last end, they merely touch and must remain separate.
        if start < last[1]:
            if end > last[1]:
                last[1] = end
        else:
            result.append([start, end])

    return result
