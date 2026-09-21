"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped. Blank lines (including a trailing newline)
are ignored. A final line without a trailing newline is still parsed.

Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order. Whitespace-only lines are skipped.
    Each remaining line is decoded with :func:`json.loads`, so duplicate
    object keys follow standard behavior (the last value wins).

    Args:
        text: The JSONL content as a string.

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
