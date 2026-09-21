"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is decoded independently with ``json.loads`` and the
results are returned in line order.  Whitespace-only lines are skipped.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.
    A final line without a trailing newline is handled.  Malformed
    non-blank JSON lines raise ``ValueError``.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
