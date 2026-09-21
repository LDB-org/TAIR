import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Unicode, CRLF line endings, and a final line without a
    trailing newline are handled. Duplicate object keys follow json.loads
    behavior (last value wins).
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        result.append(json.loads(line))
    return result
