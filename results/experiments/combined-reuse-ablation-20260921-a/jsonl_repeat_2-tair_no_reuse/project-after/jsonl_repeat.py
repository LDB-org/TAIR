import json


def parse_jsonl(text):
    """Parse JSON Lines text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys follow standard json.loads behavior
    (last value wins).
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        result.append(json.loads(line))
    return result
