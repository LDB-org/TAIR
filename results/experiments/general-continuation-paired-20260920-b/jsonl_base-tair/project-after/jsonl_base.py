import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is still parsed. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys follow json.loads semantics (last
    value wins).
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results
