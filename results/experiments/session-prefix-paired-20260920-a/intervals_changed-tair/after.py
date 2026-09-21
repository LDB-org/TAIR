def merge_intervals(items):
    if not items:
        return []
    sorted_items = sorted(items, key=lambda x: x[0])
    merged = [list(sorted_items[0])]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        if start < last[1] or (start == last[1] and end == last[1]):
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])
    return merged
