"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is decoded independently with :func:`json.loads`.
Blank (whitespace-only) lines are skipped. Lines are processed in order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Args:
        text: A string containing JSON Lines data.

    Returns:
        A list of decoded JSON values, one per non-blank line, in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
