def merge_intervals(items):
    """Merge overlapping intervals and intervals whose endpoints touch.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Does not mutate any input list and does not share mutable sublists
    with it. Empty input returns [].
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) without mutating input.
    sorted_items = sorted(items, key=lambda x: (x[0], x[1]))

    merged = []
    for interval in sorted_items:
        start, end = interval[0], interval[1]
        if not merged or start > merged[-1][1]:
            # No overlap/touch with the last merged interval.
            merged.append([start, end])
        else:
            # Overlap or touch: extend the last merged interval.
            if end > merged[-1][1]:
                merged[-1][1] = end

    return merged
