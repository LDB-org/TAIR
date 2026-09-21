"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped. Unicode, CRLF line endings, and a final
line without a trailing newline are all handled.

Malformed non-blank JSON lines raise ValueError. Duplicate object keys at any
nesting depth raise ValueError.
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
    """Parse JSONL text into a list of decoded JSON values.

    Args:
        text: A string containing zero or more JSON values, one per line.

    Returns:
        A list of decoded JSON values in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON, or if any
            object contains duplicate keys at any nesting depth.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_keys,
            )
        except json.JSONDecodeError as exc:
            raise ValueError("malformed JSON line: %s" % (exc,)) from exc
        values.append(value)
    return values
