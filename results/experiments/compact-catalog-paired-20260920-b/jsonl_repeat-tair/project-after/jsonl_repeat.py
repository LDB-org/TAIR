"""Parse newline-delimited JSON (JSONL) text."""
import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a
    final line without a trailing newline are handled. Malformed nonblank
    JSON lines raise ValueError. Duplicate object keys follow json.loads
    behavior: the last value wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
