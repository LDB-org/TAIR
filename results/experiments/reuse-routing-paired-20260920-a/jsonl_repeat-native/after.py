"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Whitespace-only lines are skipped.  A final line without a trailing
newline is handled.  Malformed non-blank lines raise :class:`ValueError`.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.
    A final line that does not end with a newline is still parsed.
    Malformed non-blank JSON lines raise :class:`ValueError`.

    Duplicate object keys follow :func:`json.loads` behaviour: the last
    value wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
