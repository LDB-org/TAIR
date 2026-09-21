import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Each non-blank line is parsed with json.loads. Whitespace-only lines are
    skipped. A final line without a trailing newline is handled. Malformed
    non-blank JSON lines raise ValueError.
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        result.append(json.loads(line))
    return result
