import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Each non-blank line is parsed as a JSON value. Whitespace-only lines are
    skipped. Malformed non-blank lines raise ValueError. CRLF line endings and
    a final line without a trailing newline are handled. Duplicate object keys
    follow standard json.loads behavior (last value wins).
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
