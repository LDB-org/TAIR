import json


def _check_duplicate_keys(pairs):
    """Reject duplicate object keys at any nesting depth."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"Duplicate object key: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Lines are processed in order. Whitespace-only lines are skipped.
    Malformed non-blank JSON lines raise ValueError. Duplicate object
    keys at any nesting depth raise ValueError.
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        result.append(json.loads(line, object_pairs_hook=_check_duplicate_keys))
    return result
