def unique_labels(values):
    """Return original strings for the first occurrence of each unique label.

    Deduplicate using Unicode casefold after stripping leading/trailing
    whitespace. Empty normalized keys are discarded. The original unmodified
    string is returned for the first occurrence of each key, preserving order.
    The input list is not mutated.
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
