def merge_intervals(items):
    if not items:
        return []
    sorted_items = sorted(items, key=lambda interval: interval[0])
    merged = [list(sorted_items[0])]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        if start < last[1]:
            if end > last[1]:
                last[1] = end
        elif start == last[1] and start == end and last[0] == last[1]:
            # zero-length interval at same point as a zero-length interval
            pass
        elif start == last[1] and last[0] == last[1] and end > last[1]:
            # zero-length interval at start of a longer interval
            last[1] = end
        else:
            merged.append([start, end])
    return merged
