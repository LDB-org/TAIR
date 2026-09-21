"""Parse newline-delimited JSON (JSONL) text into a list of values."""

import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per nonblank line, in order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings and a final
    line without a trailing newline are handled. Malformed nonblank JSON lines
    raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
