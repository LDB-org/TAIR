"""Parse JSON Lines (JSONL) text into a list of decoded JSON values."""

import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, in line order.

    Skips whitespace-only lines. Handles Unicode, CRLF, and a final line
    without a newline. Malformed non-blank JSON lines raise ValueError.
    """
    result = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        result.append(json.loads(line))
    return result
