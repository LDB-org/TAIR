"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Whitespace-only lines are skipped. Blank lines (including a trailing
line without a newline) are handled gracefully. Malformed non-blank
JSON lines raise :class:`ValueError`.
"""

import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per non-blank line.

    Args:
        text: A string containing JSON Lines data.

    Returns:
        A list of decoded JSON values in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
