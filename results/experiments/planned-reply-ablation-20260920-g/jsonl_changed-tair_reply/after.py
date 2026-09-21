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

    - Skips whitespace-only lines.
    - Handles Unicode, CRLF, and a final line without a trailing newline.
    - Raises ValueError for malformed non-blank JSON lines.
    - Rejects duplicate object keys at any nesting depth.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            results.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON line: {line!r}") from exc
    return results
