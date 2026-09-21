import json


def _scan_value(text, idx, decoder):
    """Scan a JSON value starting at idx, recursing into objects/arrays.

    Returns the index after the value. Raises ValueError on duplicate object
    keys at any nesting depth.
    """
    length = len(text)
    while idx < length and text[idx] in ' \t\n\r':
        idx += 1
    if idx >= length:
        raise ValueError("unexpected end of input")
    if text[idx] == '{':
        return _scan_object(text, idx, decoder)
    if text[idx] == '[':
        return _scan_array(text, idx, decoder)
    _, idx = decoder.raw_decode(text, idx)
    return idx


def _scan_object(text, idx, decoder):
    """Scan a JSON object starting at '{', rejecting duplicate keys."""
    length = len(text)
    idx += 1  # skip '{'
    seen = set()
    while True:
        while idx < length and text[idx] in ' \t\n\r':
            idx += 1
        if idx < length and text[idx] == '}':
            return idx + 1
        # Parse key string
        if idx >= length or text[idx] != '"':
            raise ValueError("invalid object key")
        key, idx = decoder.raw_decode(text, idx)
        if key in seen:
            raise ValueError(f"duplicate key: {key!r}")
        seen.add(key)
        while idx < length and text[idx] in ' \t\n\r':
            idx += 1
        if idx >= length or text[idx] != ':':
            raise ValueError("expected ':'")
        idx += 1
        # Scan value (recursively scanning nested objects/arrays)
        idx = _scan_value(text, idx, decoder)
        while idx < length and text[idx] in ' \t\n\r':
            idx += 1
        if idx < length and text[idx] == ',':
            idx += 1
            continue
        if idx < length and text[idx] == '}':
            return idx + 1
        raise ValueError("expected ',' or '}'")


def _scan_array(text, idx, decoder):
    """Scan a JSON array starting at '[', recursing into elements."""
    length = len(text)
    idx += 1  # skip '['
    while True:
        while idx < length and text[idx] in ' \t\n\r':
            idx += 1
        if idx < length and text[idx] == ']':
            return idx + 1
        idx = _scan_value(text, idx, decoder)
        while idx < length and text[idx] in ' \t\n\r':
            idx += 1
        if idx < length and text[idx] == ',':
            idx += 1
            continue
        if idx < length and text[idx] == ']':
            return idx + 1
        raise ValueError("expected ',' or ']'")


def _reject_duplicate_keys(text):
    """Reject duplicate object keys at any nesting depth in raw JSON text.

    json.loads silently keeps the last occurrence of a duplicate key, so
    duplicate detection must operate on the raw text before decoding.
    """
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length:
        idx = _scan_value(text, idx, decoder)


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Malformed non-blank JSON lines raise
    ValueError. Unicode, CRLF line endings, and a final line without a
    trailing newline are handled. Duplicate object keys at any nesting depth
    raise ValueError.
    """
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        _reject_duplicate_keys(line)
        value = json.loads(line)
        result.append(value)
    return result
