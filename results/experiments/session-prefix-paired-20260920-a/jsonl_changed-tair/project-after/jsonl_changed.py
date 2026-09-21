import json


def _reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Malformed non-blank JSON lines raise ValueError.
    Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line, object_pairs_hook=_reject_duplicates))
    return results
