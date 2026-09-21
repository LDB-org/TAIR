"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value. Blank lines
(whitespace-only) are skipped. Malformed non-blank lines raise ValueError.
Duplicate object keys at any nesting depth raise ValueError.
"""

import json


def _reject_duplicate_keys(pairs):
    """Object-pairs hook that rejects duplicate keys with ValueError."""
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate object key: %r" % (key,))
        seen[key] = value
    return seen


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Unicode and CRLF line endings are supported.
    Malformed non-blank JSON lines raise ValueError. Duplicate object
    keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(
            json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        )
    return results
