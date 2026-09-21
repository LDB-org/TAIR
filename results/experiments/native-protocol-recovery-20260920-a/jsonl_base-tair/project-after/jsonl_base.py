import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Malformed non-blank lines raise ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
