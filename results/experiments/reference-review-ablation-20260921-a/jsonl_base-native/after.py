"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Blank lines (whitespace-only) are skipped. Malformed non-blank lines
raise :class:`ValueError`.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Malformed non-blank JSON lines raise
    :class:`ValueError`. Duplicate object keys follow :func:`json.loads`
    behavior (last value wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
