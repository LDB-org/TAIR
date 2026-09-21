def merge_intervals(items):
    """Merge a list of [start, end] intervals.

    Args:
        items: A list of two-element lists [start, end] with integers and
            start <= end.

    Returns:
        A new sorted list of merged two-element lists. Overlapping intervals
        and intervals whose endpoints touch are merged. The input list is not
        mutated and no mutable sublists are shared with it. Empty input
        returns [].
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) so the input is not
    # mutated. Each interval is copied into a fresh list.
    sorted_intervals = sorted(([start, end] for start, end in items),
                              key=lambda iv: (iv[0], iv[1]))

    merged = [sorted_intervals[0][:]]
    for start, end in sorted_intervals[1:]:
        last = merged[-1]
        if start <= last[1]:
            # Overlap or touching endpoints: extend the last interval.
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
