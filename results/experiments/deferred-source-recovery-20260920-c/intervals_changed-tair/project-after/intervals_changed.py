def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Only strictly overlapping intervals are merged; intervals whose
    endpoints merely touch remain separate. Zero-length intervals are
    allowed. The input is not mutated and no mutable sublists are shared
    with it.
    """
    if not items:
        return []

    # Work on copies so we never mutate the input or share sublists.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0]]
    for start, end in sorted_items[1:]:
        last_start, last_end = merged[-1]
        if start < last_end:  # strictly overlapping only
            if end > last_end:
                merged[-1] = [last_start, end]
        elif start == last_end and start == end and last_start == last_end:
            # Two zero-length intervals at the same point strictly overlap
            merged[-1] = [last_start, end]
        else:
            merged.append([start, end])

    return merged
