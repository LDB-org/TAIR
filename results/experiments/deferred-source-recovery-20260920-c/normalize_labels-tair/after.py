"""Deduplicate a list of strings by Unicode casefold, preserving first occurrence."""


def unique_labels(values):
    """Return a new list keeping the first occurrence of each distinct label.

    Keys are computed by stripping leading/trailing whitespace and applying
    Unicode casefold. Empty normalized keys are discarded. The original
    unmodified string is returned for the first occurrence of each key,
    preserving order. The input list is not mutated.
    """
    seen = set()
    result = []
    for value in values:
        key = value.strip().casefold()
        if not key:
            continue
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
