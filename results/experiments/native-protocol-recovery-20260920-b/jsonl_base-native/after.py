"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a string containing
one JSON value per line and returns the decoded values in line order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text and return a list of decoded JSON values in line order.

    Whitespace-only lines are skipped.  The text may use CRLF or LF line
    endings, and a final line need not end with a newline.  Any non-blank
    line that is not valid JSON raises :class:`ValueError`.

    Duplicate object keys follow standard :func:`json.loads` behavior: the
    last value wins.

    Args:
        text: A string containing JSON Lines data.

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
