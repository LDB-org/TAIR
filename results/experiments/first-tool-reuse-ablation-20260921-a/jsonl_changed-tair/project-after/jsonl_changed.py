import json


def _reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line, object_pairs_hook=_reject_duplicates))
    return results
