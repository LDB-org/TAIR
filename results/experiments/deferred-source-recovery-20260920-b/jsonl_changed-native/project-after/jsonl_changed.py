"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently as a JSON value.  Blank lines
(containing only whitespace) are skipped.  The result preserves line order.

Features:
  * Handles Unicode text.
  * Handles CRLF line endings and a final line without a trailing newline.
  * Rejects duplicate object keys at any nesting depth with ``ValueError``.
  * Raises ``ValueError`` for malformed non-blank JSON lines.
  * No import-time I/O; uses only the standard library.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json`` calls this hook for every object it decodes, at any nesting
    depth, so this catches duplicate keys throughout the document.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Blank lines (whitespace-only) are skipped.  Malformed non-blank JSON
    lines raise ``ValueError``.  Duplicate object keys at any nesting depth
    also raise ``ValueError``.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON line: {}".format(exc)) from exc
    return values
