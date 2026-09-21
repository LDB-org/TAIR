"""Parse JSON Lines (JSONL) text into a list of decoded JSON values."""

import json


def parse_jsonl(text):
    """Parse JSONL text and return a list of decoded JSON values in line order.

    - Skips whitespace-only lines.
    - Handles Unicode, CRLF line endings, and a final line without a newline.
    - Raises ValueError for malformed non-blank JSON lines.
    - Duplicate object keys follow standard json.loads behavior (last wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
