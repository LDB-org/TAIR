import json


def _reject_duplicate_keys(pairs):
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate object key: {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _check_duplicates(value):
    if isinstance(value, dict):
        for key, item in value.items():
            _check_duplicates(item)
    elif isinstance(value, list):
        for item in value:
            _check_duplicates(item)


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is still parsed. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise
    ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        _check_duplicates(value)
        results.append(value)
    return results
