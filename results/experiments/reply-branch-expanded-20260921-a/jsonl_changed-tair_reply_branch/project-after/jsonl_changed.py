import json


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key: {key!r}")
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
            results.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON line: {exc}") from exc
    return results
