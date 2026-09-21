"""Parse newline-delimited JSON (JSON Lines) text into a list of values."""
import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per nonblank line, in order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a final
    line without a trailing newline are all handled. Malformed nonblank JSON
    lines raise ValueError. Duplicate object keys follow json.loads behavior
    (the last value wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
