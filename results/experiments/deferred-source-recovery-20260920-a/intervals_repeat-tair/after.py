def merge_intervals(items):
    """Merge overlapping/touching intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Does not mutate any input list and does not share mutable sublists
    with it. Empty input returns [].
    """
    if not items:
        return []

    # Sort by start, then by end, without mutating the input.
    sorted_items = sorted(items, key=lambda iv: (iv[0], iv[1]))

    merged = []
    for start, end in sorted_items:
        if not merged or start > merged[-1][1]:
            # No overlap/touch with the last merged interval.
            merged.append([start, end])
        else:
            # Overlap or touch: extend the last merged interval.
            if end > merged[-1][1]:
                merged[-1][1] = end

    return merged
