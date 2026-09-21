"""Parse JSON Lines (JSONL) text into a list of decoded JSON values."""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    - Whitespace-only lines are skipped.
    - Handles Unicode, CRLF line endings, and a final line without a newline.
    - Malformed non-blank JSON lines raise ValueError.
    - Duplicate object keys follow standard json.loads behavior (last wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
