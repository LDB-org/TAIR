"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is decoded independently with :func:`json.loads`.
Whitespace-only lines are skipped. Lines are processed in order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Args:
        text: A string containing JSON Lines data.

    Returns:
        A list of decoded JSON values, one per non-blank line.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
