import json


def _object_pairs_hook(pairs):
    """Reject duplicate object keys at any nesting depth."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate object key {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Lines are processed in order. Whitespace-only lines are skipped.
    Malformed non-blank JSON lines raise ValueError.
    Duplicate object keys at any nesting depth raise ValueError.
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line, object_pairs_hook=_object_pairs_hook)
        result.append(value)
    return result
