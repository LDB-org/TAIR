def merge_intervals(items):
    """Merge overlapping or touching intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    The input is not mutated and no mutable sublists are shared with it.
    """
    if not items:
        return []

    # Work on copies so we never mutate the input or share sublists.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:  # overlap or touching endpoints
            if end > last_end:
                merged[-1] = [last_start, end]
        else:
            merged.append([start, end])

    return merged
