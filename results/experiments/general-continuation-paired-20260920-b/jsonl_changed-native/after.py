"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped.  Malformed non-blank JSON lines raise
ValueError.  Duplicate object keys at any nesting depth raise ValueError.
"""

import json


def _reject_duplicate_keys(pairs):
    """object_pairs_hook that rejects duplicate keys at any nesting depth."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate object key: %r" % (key,))
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped.  Malformed non-blank JSON lines raise
    ValueError.  Duplicate object keys at any nesting depth raise ValueError.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    results = []
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
        results.append(value)
    return results
