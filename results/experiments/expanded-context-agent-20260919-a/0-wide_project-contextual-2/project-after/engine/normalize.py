def unique_names(names):
    seen = set()
    result = []
    for name in names:
        stripped = name.strip()
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(stripped)
    return result
    return sorted(set(names))
