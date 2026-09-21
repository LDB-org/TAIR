import json


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicates(pairs):
    """Reject duplicate object keys. Called as object_pairs_hook."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise _DuplicateKeyError("duplicate object key: %r" % (key,))
        obj[key] = value
    return obj


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Duplicate object keys at any nesting depth raise ValueError.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicates)
        except _DuplicateKeyError as exc:
            raise ValueError(str(exc)) from exc
        results.append(value)
    return results
