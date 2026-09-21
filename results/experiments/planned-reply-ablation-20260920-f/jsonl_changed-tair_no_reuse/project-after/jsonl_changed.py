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
    """Parse JSON Lines text into a list of decoded JSON values, in line order.

    - Skips whitespace-only lines.
    - Handles Unicode, CRLF, and a final line without a newline.
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
            raise ValueError(f"Malformed JSON line: {line!r}") from exc
    return results
