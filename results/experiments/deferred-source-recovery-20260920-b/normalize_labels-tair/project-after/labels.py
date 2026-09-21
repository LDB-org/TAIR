def unique_labels(values):
    """Return first occurrence of each string, deduplicated by casefolded stripped key."""
    seen = set()
    result = []
    for value in values:
        key = value.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
