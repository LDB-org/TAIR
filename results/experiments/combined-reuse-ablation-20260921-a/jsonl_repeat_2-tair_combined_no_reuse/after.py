import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Skips whitespace-only lines. Handles Unicode, CRLF, and a final line
    without a trailing newline. Malformed non-blank JSON lines raise
    ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
