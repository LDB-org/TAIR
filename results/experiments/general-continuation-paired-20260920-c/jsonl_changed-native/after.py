"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a JSONL string and
returns the decoded JSON values in line order.  It is intentionally free of
any import-time I/O and uses only the standard library.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json.loads`` calls this hook for every object encountered, at any
    nesting depth.  If a key appears more than once within the same object,
    a :class:`ValueError` is raised.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Each non-blank line is decoded independently and appended to the result
    in line order.  Blank lines (containing only whitespace) are skipped.
    The final line does not need to end with a newline.  Both ``\\n`` and
    ``\\r\\n`` line endings are supported, and Unicode content is handled
    transparently.

    Raises:
        ValueError: If a non-blank line contains malformed JSON, or if any
            object (at any nesting depth) contains duplicate keys.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise ValueError("malformed JSON line: {!r}".format(line)) from exc
        values.append(value)
    return values
