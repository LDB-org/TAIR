"""Parse newline-delimited JSON (JSON Lines) text into a list of values."""
import json


def _object_pairs(pairs):
    """Reject duplicate object keys at any nesting depth."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate object key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per nonblank line, in order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a final
    line without a trailing newline are all handled. Malformed nonblank JSON
    lines raise ValueError. Duplicate object keys at any nesting depth raise
    ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line, object_pairs_hook=_object_pairs)
        values.append(value)
    return values
