def merge_intervals(items):
    if not items:
        return []
    # Work on copies so we never mutate or share sublists with the input.
    intervals = sorted([list(interval) for interval in items])
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = [last_start, max(last_end, end)]
        else:
            merged.append([start, end])
    return merged
