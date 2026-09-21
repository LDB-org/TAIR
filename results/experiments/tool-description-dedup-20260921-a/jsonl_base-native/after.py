"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Blank lines (whitespace-only) are skipped. Lines are returned in order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values.

    Args:
        text: A string containing zero or more JSON values, one per line.

    Returns:
        A list of decoded JSON values, in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
