def merge_intervals(items):
    """Merge overlapping intervals and intervals whose endpoints touch.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a new sorted list of merged two-element lists.
    The input list and its sublists are not mutated, and no mutable
    sublists are shared with the input.
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) without mutating input.
    sorted_items = sorted(items, key=lambda x: (x[0], x[1]))

    merged = []
    for interval in sorted_items:
        # Copy the interval so we never share mutable sublists with input.
        current = [interval[0], interval[1]]
        if not merged:
            merged.append(current)
        else:
            last = merged[-1]
            # Overlap or touching endpoints: current.start <= last.end
            if current[0] <= last[1]:
                if current[1] > last[1]:
                    last[1] = current[1]
            else:
                merged.append(current)

    return merged
