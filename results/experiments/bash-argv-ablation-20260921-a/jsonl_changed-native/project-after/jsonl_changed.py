"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value. Whitespace-only
lines are skipped. A final line without a trailing newline is handled.
Duplicate object keys at any nesting depth are rejected with ValueError.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from key/value pairs, rejecting duplicate keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: %r" % (key,))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Malformed non-blank JSON lines raise ValueError.
    Duplicate object keys at any nesting depth raise ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON on line: %r" % (line,)) from exc
        values.append(value)
    return values
