import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Lines are processed in order. Whitespace-only lines are skipped.
    Malformed non-blank JSON lines raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
