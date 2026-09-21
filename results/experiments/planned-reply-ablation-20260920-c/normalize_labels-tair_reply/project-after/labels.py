def unique_labels(values):
    """Return unique strings preserving first occurrence order.

    Deduplication key: the string stripped of leading/trailing whitespace and
    Unicode casefolded. Empty normalized keys are discarded. The original
    unmodified string is returned for the first occurrence of each key.
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
