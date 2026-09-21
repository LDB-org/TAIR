import json


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate object key: {key!r}")
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. Unicode, CRLF line endings, and a final
    line without a trailing newline are handled. Malformed non-blank JSON lines
    raise ValueError. Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON line: {line!r}") from exc
        results.append(value)
    return results
