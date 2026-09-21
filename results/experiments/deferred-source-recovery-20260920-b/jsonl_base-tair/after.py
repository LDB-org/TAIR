"""Parse JSON Lines (JSONL) text into a list of decoded values."""

import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per nonblank line.

    Whitespace-only lines are skipped. Unicode, CRLF line endings and a
    final line without a trailing newline are handled. Malformed nonblank
    JSON lines raise ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
