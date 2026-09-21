"""Deduplicate a list of strings by Unicode casefolded, whitespace-stripped keys."""


def unique_labels(values):
    """Return the first occurrence of each label, deduplicated by normalized key.

    A label's key is its value with leading/trailing whitespace stripped and
    then Unicode casefolded. Empty normalized keys are discarded. The original
    (unmodified) string is returned for the first occurrence of each key,
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
