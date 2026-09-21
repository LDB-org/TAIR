def merge_intervals(items):
    if not items:
        return []
    # Sort by start, then end
    sorted_items = sorted(items, key=lambda x: (x[0], x[1]))
    merged = [list(sorted_items[0])]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        if start < last[1]:
            # Strictly overlapping: merge
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])
    return merged
