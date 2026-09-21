"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped. Blank lines (including a trailing newline)
are ignored. A final line without a trailing newline is still parsed.

Malformed non-blank JSON lines raise ValueError.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values.

    Args:
        text: A string containing JSON Lines data.

    Returns:
        A list of decoded JSON values, one per non-blank line, in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
