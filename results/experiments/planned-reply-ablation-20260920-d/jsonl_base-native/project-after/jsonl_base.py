"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped. A final line without a trailing newline is
handled. Malformed non-blank JSON lines raise ValueError.
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
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
