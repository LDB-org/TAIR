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
    sorted_items = sorted(([start, end] for start, end in items))

    result = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last = result[-1]
        # Strict overlap: current start < last end. Touching (==) stays separate.
        if start < last[1]:
            if end > last[1]:
                last[1] = end
        else:
            result.append([start, end])

    return result
