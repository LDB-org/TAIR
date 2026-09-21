"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a JSONL document
(string) and returns a list of the decoded JSON values in line order.

Only the standard library is used.  No I/O is performed at import time.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json.loads`` calls this hook for every object it decodes, at any
    nesting depth.  If a key appears more than once within the same
    object, a :class:`ValueError` is raised.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Each non-blank line is decoded independently, in line order.  Lines
    that contain only whitespace are skipped.  A final line without a
    trailing newline is handled.  Unicode and CRLF line endings are
    supported.

    Raises:
        ValueError: If a non-blank line contains malformed JSON, or if
            any object (at any nesting depth) contains duplicate keys.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError("malformed JSON line: {!r}".format(line)) from exc
    return values
