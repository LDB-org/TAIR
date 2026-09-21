"""Parse JSON Lines text into a list of decoded JSON values."""

import json


def _reject_duplicate_keys(pairs):
    """Reject duplicate object keys at any nesting depth."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"duplicate object key: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_jsonl(text):
    """Return a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. Unicode, CRLF and a final line
    without a newline are handled. Malformed nonblank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise
    ValueError.
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            result.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON line: {line!r}") from exc
    return result
