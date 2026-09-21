"""Interval merging utilities."""

from typing import List


def merge_intervals(items: List[List[int]]) -> List[List[int]]:
    """Merge a list of [start, end] intervals.

    Input is a list of two-element lists [start, end] with integers and
    start <= end. Returns a sorted list of merged two-element lists.

    Overlapping intervals and intervals whose endpoints touch are merged.
    The input list and its sublists are not mutated, and no mutable sublists
    are shared with the input.

    Empty input returns [].
    """
    if not items:
        return []

    # Work on a copy of the intervals so we never mutate the input.
    intervals = sorted(([start, end] for start, end in items))

    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # Overlap or touching endpoints -> merge.
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    return merged
