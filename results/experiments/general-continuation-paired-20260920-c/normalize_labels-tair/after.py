def unique_labels(values):
    """Deduplicate strings using Unicode casefold after stripping whitespace.

    Input is a list of strings. Each value is stripped of leading and trailing
    whitespace, then casefolded to form a key. Empty normalized keys are
    discarded. The original unmodified string is returned for the first
    occurrence of each key, preserving order. The input is not mutated.
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
