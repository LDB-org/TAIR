"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with the standard library
``json`` module. Whitespace-only lines are skipped. Lines may be
terminated by ``\\n``, ``\\r\\n``, or a final line without a newline.
Malformed non-blank lines raise :class:`ValueError`.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Values are returned in line order. Whitespace-only lines are
    skipped. A final line without a trailing newline is handled.
    Malformed non-blank JSON lines raise :class:`ValueError`.

    Duplicate object keys follow standard ``json.loads`` behavior: the
    last value wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
