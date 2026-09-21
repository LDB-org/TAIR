import json


def _reject_duplicate_keys(pairs):
    """Reject duplicate object keys at any nesting depth."""
    seen = set()
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"Duplicate object key: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Each non-blank line is parsed with json.loads. Whitespace-only lines are
    skipped. A final line without a trailing newline is handled. Malformed
    non-blank JSON lines raise ValueError. Duplicate object keys at any
    nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
    return results
