def unique_labels(values):
    """Return first occurrence of each string, deduplicated by Unicode casefold.

    Leading and trailing whitespace is stripped before computing the
    casefolded key. Empty normalized keys are discarded. The original
    unmodified string is kept for the first occurrence of each key, in
    order. The input list is not mutated.
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
