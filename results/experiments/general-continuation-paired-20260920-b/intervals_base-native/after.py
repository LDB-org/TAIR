"""Interval merging utilities."""

from typing import List


def merge_intervals(items: List[List[int]]) -> List[List[int]]:
    """Merge overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.
    Overlapping intervals and intervals whose endpoints touch are merged.

    The input list and its sublists are not mutated, and no mutable
    sublists are shared with the input.
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) so we don't mutate input.
    sorted_items = sorted(([start, end] for start, end in items))

    merged = [sorted_items[0][:]]
    for start, end in sorted_items[1:]:
        last = merged[-1]
        # Overlap or touch (end >= last_start) => merge.
        if start <= last[1]:
            if end > last[1]:
                last[1] = end
        else:
            merged.append([start, end])

    return merged
