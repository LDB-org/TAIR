"""Parse JSON Lines (JSONL) text into a list of decoded JSON values."""

import json


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per non-blank line, in order.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys follow json.loads behavior (last wins).
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON line: {line!r}") from exc
    return results
