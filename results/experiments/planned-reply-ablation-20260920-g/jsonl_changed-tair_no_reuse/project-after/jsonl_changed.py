import json


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a
    final line without a trailing newline are handled. Malformed non-blank
    JSON lines raise ValueError. Duplicate object keys at any nesting depth
    raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            results.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON line: {line!r}") from exc
    return results
