"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Whitespace-only lines are skipped.  A final line without a trailing
newline is handled.  Malformed non-blank lines raise :class:`ValueError`.
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
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
