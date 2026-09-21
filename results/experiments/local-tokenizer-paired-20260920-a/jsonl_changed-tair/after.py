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


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Blank and whitespace-only lines are skipped. A final line without a
    trailing newline is handled. Malformed non-blank lines raise ValueError.
    Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
    return results
