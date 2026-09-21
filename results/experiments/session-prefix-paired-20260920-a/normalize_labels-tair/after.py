def unique_labels(values):
    """Return original strings for the first occurrence of each casefolded key.

    Leading/trailing whitespace is stripped to form the key; empty normalized
    keys are discarded. The original unmodified string is kept for the first
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
