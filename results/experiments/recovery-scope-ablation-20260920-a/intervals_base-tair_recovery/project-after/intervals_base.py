def merge_intervals(items):
    """Merge overlapping intervals and intervals whose endpoints touch.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A sorted list of merged two-element lists. Empty input returns [].

    The input list is not mutated, and no mutable sublists are shared with it.
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) to avoid mutating input.
    sorted_items = sorted(items, key=lambda x: (x[0], x[1]))

    merged = []
    for start, end in sorted_items:
        if not merged:
            merged.append([start, end])
        else:
            last_start, last_end = merged[-1]
            # Overlap or touch: current start <= last_end + 1
            if start <= last_end + 1:
                if end > last_end:
                    merged[-1][1] = end
            else:
                merged.append([start, end])

    return merged
