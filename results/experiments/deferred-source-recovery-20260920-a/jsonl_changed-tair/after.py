"""Parse newline-delimited JSON (JSONL) text."""
import json


def _reject_duplicate_keys(value):
    """Raise ValueError if any object at any depth has duplicate keys."""
    if isinstance(value, dict):
        seen = set()
        for key in value:
            if key in seen:
                raise ValueError("duplicate object key: %r" % (key,))
            seen.add(key)
            _reject_duplicate_keys(value[key])
    elif isinstance(value, list):
        for item in value:
            _reject_duplicate_keys(item)


def parse_jsonl(text):
    """Return a list of decoded JSON values, one per nonblank line."""
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        _reject_duplicate_keys(value)
        results.append(value)
    return results
