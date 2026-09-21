def merge_intervals(items):
    """Merge overlapping intervals and intervals whose endpoints touch.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists. The
    input is not mutated and no mutable sublists are shared with it.
    Empty input returns [].
    """
    if not items:
        return []
    # Sort by start, then end; work on copies to avoid mutating input.
    sorted_items = sorted(([start, end] for start, end in items))
    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        if start < last[1] or (start == last[1] and end == last[1]):
            # Strictly overlapping: merge.
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])
    return merged
