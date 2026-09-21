import json


def _no_duplicates(pairs):
    """object_pairs_hook that rejects duplicate keys at any nesting depth."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate object key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Skips whitespace-only lines. Handles Unicode, CRLF, and a final line
    without a trailing newline. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_no_duplicates)
        except ValueError as exc:
            raise ValueError(f"Malformed JSON line: {line!r}") from exc
        results.append(value)
    return results
