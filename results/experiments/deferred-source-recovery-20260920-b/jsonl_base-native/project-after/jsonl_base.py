"""JSON Lines parsing utilities.

Provides parse_jsonl(text) which decodes a JSON Lines document into a list
of JSON values, in line order.
"""

import json


def parse_jsonl(text):
    """Parse a JSON Lines document into a list of decoded JSON values.

    Each non-blank line is decoded independently with ``json.loads`` and the
    results are returned in line order. Whitespace-only lines are skipped.

    Args:
        text: The JSON Lines document as a string.

    Returns:
        A list of decoded JSON values, one per non-blank line, in line order.

    Raises:
        ValueError: If any non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        values.append(json.loads(line))
    return values
