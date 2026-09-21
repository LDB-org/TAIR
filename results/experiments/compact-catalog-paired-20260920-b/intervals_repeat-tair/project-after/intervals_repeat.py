def merge_intervals(items):
    """Merge overlapping/touching intervals."""
    if not items:
        return []
    # Sort by start, then end; copy to avoid mutating input
    sorted_items = sorted(items, key=lambda x: (x[0], x[1]))
    result = [list(sorted_items[0])]
    for start, end in sorted_items[1:]:
        last = result[-1]
        if start <= last[1]:
            if end > last[1]:
                last[1] = end
        else:
            result.append([start, end])
    return result
