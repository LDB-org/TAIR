"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value using
``json.loads``.  Whitespace-only lines are skipped.  Lines are processed
in order, so the returned list preserves the input line order.

The module performs no I/O at import time.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Args:
        text: A string containing zero or more JSON values, one per line.

    Returns:
        A list of the decoded JSON values, in line order.  Whitespace-only
        lines are skipped.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
