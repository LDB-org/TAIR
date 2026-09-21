"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a string containing
one JSON value per line and returns the decoded values in line order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values.

    Each non-blank line is decoded with :func:`json.loads` and the results
    are returned in line order. Whitespace-only lines are skipped. A final
    line without a trailing newline is handled. Unicode and CRLF line
    endings are supported.

    Args:
        text: The JSONL text to parse.

    Returns:
        A list of decoded JSON values, in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
