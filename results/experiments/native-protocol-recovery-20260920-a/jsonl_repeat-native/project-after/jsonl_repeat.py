"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value, in line order.
Whitespace-only lines are skipped. Blank lines (including those produced by
CRLF line endings) are ignored. A final line without a trailing newline is
handled. Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order. Whitespace-only lines are skipped. Each
    remaining line must contain a single valid JSON value; otherwise a
    ``ValueError`` is raised. Duplicate object keys follow standard
    ``json.loads`` behavior (the last value wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
