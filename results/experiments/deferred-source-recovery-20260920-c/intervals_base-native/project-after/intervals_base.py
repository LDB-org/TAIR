"""Interval merging utilities."""

from typing import List


def merge_intervals(items: List[List[int]]) -> List[List[int]]:
    """Merge overlapping intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    Intervals that overlap or whose endpoints touch are merged. The input
    list is not mutated and no mutable sublists are shared with it.
    Empty input returns [].
    """
    if not items:
        return []

    # Sort a copy of the intervals by start (then end) so the input is
    # not mutated.
    sorted_items = sorted(items, key=lambda iv: (iv[0], iv[1]))

    merged: List[List[int]] = []
    for start, end in sorted_items:
        if not merged:
            merged.append([start, end])
            continue

        last_start, last_end = merged[-1]
        # Overlap or touching endpoints (start <= last_end) -> merge.
        if start <= last_end:
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
