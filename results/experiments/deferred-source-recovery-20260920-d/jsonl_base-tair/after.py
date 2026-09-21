import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values."""
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
