"""Utilities for deduplicating labels."""

from typing import List


def unique_labels(values: List[str]) -> List[str]:
    """Return the first occurrence of each label, deduplicated by Unicode casefold.

    Labels are normalized by stripping leading/trailing whitespace and applying
    Unicode casefold. Empty normalized keys are discarded. The original,
    unmodified string is returned for the first occurrence of each key, in
    order of first appearance. The input list is not mutated.
    """
    seen = set()
    result = []
    for value in values:
        key = value.strip().casefold()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
