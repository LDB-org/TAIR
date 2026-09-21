def unique_labels(values):
    """Return unique strings from values, deduplicated by Unicode casefold.

    Each string is stripped of leading/trailing whitespace, then casefolded
    to form a key. Empty normalized keys are discarded. The original
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
