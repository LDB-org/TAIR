def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    - Only strictly overlapping intervals are merged. Intervals whose
      endpoints merely touch (e.g. [1,2] and [2,3]) remain separate.
    - Zero-length intervals (start == end) are allowed.
    - The input list is not mutated, and no mutable sublists are shared
      with it.
    - Empty input returns [].
    """
    if not items:
        return []

    # Work on a sorted copy of the input so we never mutate the caller's list.
    sorted_items = sorted(items, key=lambda iv: (iv[0], iv[1]))

    merged = []
    for start, end in sorted_items:
        if not merged:
            merged.append([start, end])
            continue

        last_start, last_end = merged[-1]

        # Strict overlap: the current interval starts before the previous
        # one ends. If it merely touches (start == last_end), keep separate.
        if start < last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
