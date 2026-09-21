import json


def _no_duplicates(pairs):
    """object_pairs_hook that rejects duplicate object keys."""
    d = {}
    for key, value in pairs:
        if key in d:
            raise ValueError(f"Duplicate object key: {key!r}")
        d[key] = value
    return d


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        value = json.loads(line, object_pairs_hook=_no_duplicates)
        results.append(value)
    return results
