"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped.  A final line without a trailing newline is
handled.  Malformed non-blank JSON lines raise ``ValueError``.  Duplicate
object keys at any nesting depth are rejected with ``ValueError``.

Only the standard library is used.  No I/O is performed at import time.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json`` calls this hook with a list of ``(key, value)`` pairs for each
    object it decodes.  If a key appears more than once, a ``ValueError`` is
    raised, which propagates out of ``json.loads``.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.  A final
    line without a trailing newline is still parsed.  Malformed non-blank JSON
    lines raise ``ValueError``.  Duplicate object keys at any nesting depth
    raise ``ValueError``.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(
            json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        )
    return values
