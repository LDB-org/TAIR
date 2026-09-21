"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed as a JSON value using the standard library's
``json.loads``.  Whitespace-only lines are skipped.  A final line without a
trailing newline is handled.  Malformed non-blank lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values in line order.

    Whitespace-only lines are skipped.  A final line without a trailing newline
    is handled.  Malformed non-blank JSON lines raise ``ValueError``.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
