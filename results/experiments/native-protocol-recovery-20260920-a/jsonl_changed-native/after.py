"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped.  Unicode, CRLF line endings and a final
line without a trailing newline are all handled.  Malformed non-blank JSON
lines raise ``ValueError``.  Duplicate object keys at any nesting depth
raise ``ValueError``.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.
    Malformed non-blank JSON lines raise ``ValueError``.  Duplicate object
    keys at any nesting depth raise ``ValueError``.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(
                json.loads(line, object_pairs_hook=_reject_duplicate_keys)
            )
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON on line: {!r}".format(line)) from exc
    return values
