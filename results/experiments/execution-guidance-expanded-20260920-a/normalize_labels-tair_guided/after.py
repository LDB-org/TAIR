def unique_labels(values):
    """Return the first occurrence of each label, deduplicated by Unicode casefold.

    Each value is stripped of leading/trailing whitespace, then normalized with
    str.casefold() to form a deduplication key. Empty normalized keys are
    discarded. The original (unmodified) string is returned for the first
    occurrence of each key, preserving order. The input list is not mutated.
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
