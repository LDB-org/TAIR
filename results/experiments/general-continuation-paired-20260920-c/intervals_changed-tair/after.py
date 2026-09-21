def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists. The
    input is not mutated and no mutable sublists are shared with it.
    """
    if not items:
        return []
    sorted_items = sorted((list(item) for item in items), key=lambda x: x[0])
    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last_start, last_end = merged[-1]
        if start < last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged
