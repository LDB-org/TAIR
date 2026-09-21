def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Intervals that merely touch (end == next start) remain separate.
    Zero-length intervals are allowed. The input is not mutated and no
    mutable sublists are shared with it.
    """
    if not items:
        return []

    # Work on copies so we never mutate the input or share sublists.
    sorted_items = sorted(([start, end] for start, end in items), key=lambda iv: (iv[0], iv[1]))

    result = []
    for start, end in sorted_items:
        if not result:
            result.append([start, end])
            continue
        last = result[-1]
        # Strict overlap: current start must be strictly less than last end.
        # Touching (start == last end) does NOT merge. Zero-length intervals
        # only merge when they strictly overlap, which they cannot unless
        # contained with a strictly larger span.
        if start < last[1]:
            if end > last[1]:
                last[1] = end
        else:
            result.append([start, end])

    return result
