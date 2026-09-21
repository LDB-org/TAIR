"""Deduplicate a list of strings by Unicode casefolded, stripped keys."""


def unique_labels(values):
    """Return the first occurrence of each label, preserving order.

    Labels are deduplicated using their Unicode casefolded, whitespace-stripped
    form as the key. Empty normalized keys are discarded. The original,
    unmodified string is returned for the first occurrence of each key.

    The input list is not mutated.
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
