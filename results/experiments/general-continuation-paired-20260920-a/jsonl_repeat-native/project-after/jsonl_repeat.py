"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a JSONL string and
returns the decoded JSON values in line order. It uses only the standard
library.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text and return a list of decoded JSON values in line order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a final
    line without a trailing newline are all handled. Malformed non-blank JSON
    lines raise :class:`ValueError`. Duplicate object keys follow the standard
    ``json.loads`` behavior, where the last value wins.

    Args:
        text: The JSONL text to parse.

    Returns:
        A list of decoded JSON values, one per non-blank line, in line order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Malformed JSON on line: {!r}".format(line)
            ) from exc
    return values
