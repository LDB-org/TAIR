"""Deduplicate a list of strings by Unicode casefolded, whitespace-stripped keys."""


def unique_labels(values):
    """Return the original strings, deduplicated by normalized key.

    The key for each value is the value with leading/trailing whitespace
    stripped and then Unicode casefolded. Empty normalized keys are
    discarded. For each distinct key, the first occurrence's original
    (unmodified) string is kept, preserving order.

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
