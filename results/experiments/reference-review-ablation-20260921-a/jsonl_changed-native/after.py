"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a JSONL string and
returns the decoded JSON values in line order.  It uses only the standard
library.
"""

import json


def _reject_duplicate_keys(pairs):
    """Object-pairs hook that rejects duplicate keys at any nesting depth."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate object key: {!r}".format(key))
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Each non-blank line is decoded as a JSON value, in line order.  Lines
    containing only whitespace are skipped.  A final line without a trailing
    newline is handled.  Both LF and CRLF line endings are supported, as is
    any Unicode content.

    Raises:
        ValueError: If a non-blank line contains malformed JSON, or if any
            object (at any nesting depth) contains duplicate keys.
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
            raise ValueError("malformed JSON line: {!r}".format(line)) from exc
        values.append(value)
    return values
