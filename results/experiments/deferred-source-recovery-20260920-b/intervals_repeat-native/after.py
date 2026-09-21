def merge_intervals(items):
    """Merge overlapping/touching intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Intervals that overlap or whose endpoints touch are merged.

    The input list is not mutated and no mutable sublists are shared with it.
    Empty input returns [].
    """
    if not items:
        return []

    # Sort by start, then by end, using copies so we don't mutate input.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:  # overlap or touching
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
