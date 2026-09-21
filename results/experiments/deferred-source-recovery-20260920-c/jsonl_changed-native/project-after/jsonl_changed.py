"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a JSONL string and
returns the decoded JSON values in line order.  It uses only the standard
library and performs no I/O at import time.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json`` calls this hook for every object encountered at any nesting
    depth.  If a key appears more than once, a :class:`ValueError` is raised.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Each non-blank line is decoded independently, in line order.  Blank
    lines (containing only whitespace) are skipped.  Both ``\\n`` and
    ``\\r\\n`` line endings are supported, and a final line without a
    trailing newline is handled.  Unicode is decoded normally.

    Raises:
        ValueError: If a non-blank line contains malformed JSON, or if any
            object (at any nesting depth) contains duplicate keys.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON on line: {!r}".format(line)) from exc
    return values
