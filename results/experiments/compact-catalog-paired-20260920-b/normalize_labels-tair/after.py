"""Deduplicate a list of strings by Unicode casefolded, stripped keys."""


def unique_labels(values):
    """Return the original unmodified string for the first occurrence of each key.

    Keys are derived by stripping leading/trailing whitespace and applying
    Unicode casefold. Empty normalized keys are discarded. Order is preserved
    and the input list is not mutated.
    """
    seen = set()
    result = []
    for value in values:
        key = value.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
