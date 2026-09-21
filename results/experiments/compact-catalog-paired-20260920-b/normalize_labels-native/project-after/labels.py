"""Utilities for deduplicating labels."""

from collections.abc import Iterable


def unique_labels(values: Iterable[str]) -> list[str]:
    """Return the first occurrence of each label, preserving order.

    Labels are deduplicated using Unicode casefold after stripping leading
    and trailing whitespace. Empty normalized keys are discarded. The
    original unmodified string is returned for the first occurrence of each
    key. The input is not mutated.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().casefold()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
