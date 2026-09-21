import json


def _reject_duplicates(pairs):
    """Reject duplicate object keys at any nesting depth.

    Called as the object_pairs_hook for json.loads, so it sees the raw
    key/value pairs before json collapses duplicate keys.
    """
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate object key: {key!r}")
        seen.add(key)
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Malformed non-blank lines raise ValueError.
    Duplicate object keys at any nesting depth raise ValueError.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line, object_pairs_hook=_reject_duplicates)
        values.append(value)
    return values
