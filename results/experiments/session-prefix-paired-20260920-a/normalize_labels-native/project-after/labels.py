"""Utilities for deduplicating labels."""

from __future__ import annotations


def unique_labels(values):
    """Return the first occurrence of each label, deduplicated by Unicode casefold.

    Input is a list of strings. Each value is normalized by stripping leading
    and trailing whitespace and applying Unicode casefold. Empty normalized
    keys are discarded. The original (unmodified) string is returned for the
    first occurrence of each key, preserving order. The input list is not
    mutated.
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
