def merge_intervals(items):
    if not items:
        return []
    intervals = sorted(([start, end] for start, end in items), key=lambda x: (x[0], x[1]))
    result = [intervals[0][:]]
    for start, end in intervals[1:]:
        last = result[-1]
        if start < last[1]:
            if end > last[1]:
                last[1] = end
        else:
            result.append([start, end])
    return result
