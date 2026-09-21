"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with ``json.loads`` and the
decoded values are returned in line order.  Whitespace-only lines are
skipped.  A final line without a trailing newline is handled correctly.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.
    Any non-blank line that is not valid JSON raises ``ValueError``.

    Duplicate object keys follow the standard ``json.loads`` behaviour:
    the last value wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
