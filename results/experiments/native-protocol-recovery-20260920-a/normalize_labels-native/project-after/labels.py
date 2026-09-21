"""Utilities for deduplicating labels."""

from __future__ import annotations


def unique_labels(values):
    """Return a new list of unique labels from ``values``.

    Each string is normalized by stripping leading/trailing whitespace and
    applying Unicode casefold. Empty normalized keys are discarded. For the
    first occurrence of each key, the original unmodified string is kept,
    preserving order. The input list is not mutated.
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
