"""Parse newline-delimited JSON (JSONL) text into a list of values."""
import json


def _object_pairs_hook(pairs):
    """Build a dict, rejecting duplicate keys at any nesting depth."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: %r" % (key,))
        result[key] = value
    return result


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per nonblank line, in order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings and a final
    line without a trailing newline are all handled. Malformed nonblank JSON
    lines raise ValueError. Duplicate object keys at any nesting depth raise
    ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line, object_pairs_hook=_object_pairs_hook)
        values.append(value)
    return values
