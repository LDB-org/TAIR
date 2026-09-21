"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is decoded independently with ``json.loads`` and the
results are returned in line order.  Blank (whitespace-only) lines are
skipped.  Unicode, CRLF line endings and a final line without a trailing
newline are all handled.  Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.  A
    malformed non-blank line raises ``ValueError``.  Duplicate object keys
    follow standard ``json.loads`` behaviour (the last value wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
