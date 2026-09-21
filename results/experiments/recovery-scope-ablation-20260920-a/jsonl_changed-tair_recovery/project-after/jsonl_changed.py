import json


def _reject_duplicate_keys(pairs):
    """Reject duplicate object keys at any nesting depth."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"Duplicate object key: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a
    final line without a trailing newline are handled. Malformed nonblank
    JSON lines raise ValueError. Duplicate object keys at any nesting depth
    raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
    return results
