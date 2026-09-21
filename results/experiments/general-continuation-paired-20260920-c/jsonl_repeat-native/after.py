"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped. A final line without a trailing newline is
handled. Malformed non-blank JSON lines raise ValueError.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values.

    Args:
        text: A string containing zero or more JSON lines.

    Returns:
        A list of decoded JSON values, in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
