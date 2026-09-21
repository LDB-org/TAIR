def unique_labels(values):
    """Return first occurrence of each value, deduplicated by Unicode casefold
    after stripping leading/trailing whitespace. Empty normalized keys are
    discarded. The input list is not mutated.
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
