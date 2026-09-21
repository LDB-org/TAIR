def merge_intervals(items):
    """Merge a list of [start, end] intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Overlapping intervals and intervals whose endpoints touch are merged.

    The input list is not mutated, and no mutable sublists are shared
    with it. Empty input returns [].
    """
    if not items:
        return []

    # Work on a sorted copy of the intervals so the input is not mutated.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0][:]]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        if start <= last[1]:
            # Overlap or touching endpoints -> merge.
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
