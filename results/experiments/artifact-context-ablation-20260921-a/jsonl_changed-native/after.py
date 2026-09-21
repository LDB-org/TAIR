"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

This module provides :func:`parse_jsonl`, which reads a JSONL string and
returns the decoded JSON values in line order.  It uses only the standard
library.
"""

import json


def _reject_duplicate_keys(pairs):
    """Build a dict from ``pairs``, rejecting duplicate keys.

    ``json.loads`` calls this hook for every object it decodes, at any
    nesting depth.  If a key appears more than once, a ``ValueError`` is
    raised.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key: {!r}".format(key))
        result[key] = value
    return result


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Each non-blank line is decoded independently, in line order.  Blank
    lines (containing only whitespace) are skipped.  Both ``\\n`` and
    ``\\r\\n`` line endings are supported, as is a final line that does not
    end with a newline.  Unicode is handled by the standard JSON decoder.

    A malformed non-blank line raises ``ValueError``.  Duplicate object
    keys at any nesting depth also raise ``ValueError``.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
    return values
