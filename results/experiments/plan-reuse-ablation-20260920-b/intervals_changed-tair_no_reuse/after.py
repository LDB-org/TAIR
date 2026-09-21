def merge_intervals(items):
    """Merge strictly overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    - Does not mutate any input list and does not share mutable sublists
      with the input.
    - Empty input returns [].
    - Merges only strictly overlapping intervals; endpoints that merely
      touch (e.g. [1,2] and [2,3]) remain separate.
    - Zero-length intervals are allowed.
    """
    if not items:
        return []

    # Work on copies so we never mutate the input lists.
    sorted_items = sorted(([start, end] for start, end in items), key=lambda x: (x[0], x[1]))

    result = [sorted_items[0][:]]
    for start, end in sorted_items[1:]:
        last = result[-1]
        # Strict overlap: current start must be strictly less than last end.
        # Touching endpoints (start == last end) do not merge.
        if start < last[1]:
            if end > last[1]:
                last[1] = end
        else:
            result.append([start, end])

    return result
