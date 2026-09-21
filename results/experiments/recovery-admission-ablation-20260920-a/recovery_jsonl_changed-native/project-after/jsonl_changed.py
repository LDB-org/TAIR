"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is decoded independently as a JSON value, in line order.
Whitespace-only lines are skipped. Unicode, CRLF line endings and a final
line without a trailing newline are all handled. Malformed non-blank JSON
lines raise ValueError. Duplicate object keys at any nesting depth raise
ValueError.
"""

import json


def _reject_duplicate_keys(pairs):
    """object_pairs_hook that rejects duplicate keys in an object."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate key: %r" % (key,))
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per non-blank line.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
    return values
