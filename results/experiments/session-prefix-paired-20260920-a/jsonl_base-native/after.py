"""JSON Lines parsing utilities.

Provides parse_jsonl(text) which decodes a JSON Lines document into a list
of JSON values, in line order.
"""

import json


def parse_jsonl(text):
    """Parse a JSON Lines string into a list of decoded JSON values.

    Each non-blank line is decoded with json.loads. Whitespace-only lines are
    skipped. A final line without a trailing newline is handled. Unicode and
    CRLF line endings are supported. Malformed non-blank lines raise
    ValueError.

    Duplicate object keys follow standard json.loads behavior: the last value
    wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
