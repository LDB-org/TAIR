def unique_labels(values):
    """Return the original unmodified string for the first occurrence of each
    distinct label, preserving order.

    Deduplication uses Unicode casefold after stripping leading and trailing
    whitespace. Empty normalized keys are discarded. The input list is not
    mutated.
    """
    seen = set()
    result = []
    for value in values:
        key = value.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
