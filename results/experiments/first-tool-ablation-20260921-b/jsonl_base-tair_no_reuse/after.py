import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Lines are processed in order. Whitespace-only lines are skipped.
    Handles Unicode, CRLF line endings, and a final line without a
    trailing newline. Malformed non-blank JSON lines raise ValueError.
    Duplicate object keys follow standard json.loads behavior (last wins).
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        result.append(json.loads(line))
    return result
