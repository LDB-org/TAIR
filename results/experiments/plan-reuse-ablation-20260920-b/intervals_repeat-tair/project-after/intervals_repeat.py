def merge_intervals(items):
    if not items:
        return []
    # Sort a copy of the input to avoid mutating it
    sorted_items = sorted(items, key=lambda x: x[0])
    result = []
    for start, end in sorted_items:
        if not result or start > result[-1][1]:
            result.append([start, end])
        else:
            if end > result[-1][1]:
                result[-1][1] = end
    return result
