def unique_labels(values):
    """Return the first occurrence of each string, deduplicated by Unicode casefold.

    Strings are stripped of leading/trailing whitespace, then normalized with
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
