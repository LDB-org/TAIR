"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped.  A final line without a trailing newline is
handled.  Unicode and CRLF line endings are supported.

Malformed non-blank JSON lines raise ``ValueError``.  Duplicate object keys at
any nesting depth also raise ``ValueError``.

Only the standard library is used; no I/O happens at import time.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json`` calls this hook for every object it decodes, at any nesting depth.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: %r" % (key,))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.  A final
    line without a trailing newline is handled.  Unicode and CRLF line endings
    are supported.

    Raises:
        ValueError: If a non-blank line contains malformed JSON, or if any
            object (at any nesting depth) contains duplicate keys.
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
            raise ValueError("invalid JSON on line: %r" % (line,)) from exc
    return values
