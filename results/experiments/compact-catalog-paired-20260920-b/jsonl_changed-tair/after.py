"""Parse newline-delimited JSON (JSONL) text."""
import json


def _object_pairs_hook(pairs):
    """Reject duplicate object keys at any nesting depth."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate object key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Return a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a
    final line without a trailing newline are handled. Malformed nonblank
    JSON lines raise ValueError. Duplicate object keys at any nesting depth
    raise ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line, object_pairs_hook=_object_pairs_hook)
        values.append(value)
    return values
