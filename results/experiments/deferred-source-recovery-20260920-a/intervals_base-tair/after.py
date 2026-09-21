def merge_intervals(items):
    """Merge overlapping/touching intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Does not mutate the input and does not share mutable sublists with it.
    """
    if not items:
        return []

    # Sort by start, then end. Work on copies to avoid mutating input.
    sorted_items = sorted(([start, end] for start, end in items), key=lambda x: (x[0], x[1]))

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        if start <= last[1]:
            # Overlap or touch: extend the last interval.
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
