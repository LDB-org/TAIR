def merge_intervals(items):
    if not items:
        return []
    intervals = sorted(([start, end] for start, end in items), key=lambda x: x[0])
    merged = [intervals[0][:]]
    for start, end in intervals[1:]:
        last = merged[-1]
        # Merge only if strictly overlapping: start < last_end, OR
        # zero-length interval contained within last (start == last_end == last_start)
        if start < last[1] or (start == last[1] and start == last[0] and end == last[1]):
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])
    return merged
