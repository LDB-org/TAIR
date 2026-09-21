import json


def _reject_duplicate_keys(pairs):
    """object_pairs_hook that rejects duplicate object keys."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate object key {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Each non-blank line is parsed as a JSON value. Whitespace-only lines are
    skipped. A final line without a trailing newline is handled. Malformed
    non-blank JSON lines raise ValueError. Duplicate object keys at any
    nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        results.append(value)
    return results
