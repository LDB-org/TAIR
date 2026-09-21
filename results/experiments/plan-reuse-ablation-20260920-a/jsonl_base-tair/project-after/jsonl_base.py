import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Each non-blank line is parsed as a JSON value. Whitespace-only lines are
    skipped. Lines may be separated by \n or \r\n, and the final line need not
    end with a newline. Malformed non-blank JSON lines raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
