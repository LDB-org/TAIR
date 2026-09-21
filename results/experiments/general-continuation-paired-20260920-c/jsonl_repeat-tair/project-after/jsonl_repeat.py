import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Unicode, CRLF line endings and a final
    line without a trailing newline are handled. Malformed non-blank JSON
    lines raise ValueError. Duplicate object keys follow json.loads behavior
    (last value wins).
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
