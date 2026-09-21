"""Parse JSON Lines (JSONL) text into a list of decoded JSON values."""

import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per non-blank line, in order.

    Whitespace-only lines are skipped. A final line without a trailing newline
    is handled. Malformed non-blank JSON lines raise ValueError. Duplicate
    object keys follow json.loads behavior (last value wins).
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
