"""JSON Lines parsing utilities.

Provides parse_jsonl(text) which decodes a JSON Lines document into a list
of Python values, one per non-blank line, in line order.
"""

import json


def parse_jsonl(text):
    """Parse a JSON Lines string into a list of decoded values.

    Each non-blank line is decoded with json.loads and appended to the
    result in line order. Blank lines (whitespace-only) are skipped.

    Args:
        text: The JSON Lines document as a string.

    Returns:
        A list of decoded JSON values, one per non-blank line.

    Raises:
        ValueError: If any non-blank line contains malformed JSON.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
