"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with the standard library
``json`` module. Blank (whitespace-only) lines are skipped. Lines are
returned in their original order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order. Whitespace-only lines are skipped.
    A final line without a trailing newline is handled. Malformed
    non-blank JSON lines raise ``ValueError``.

    Duplicate object keys follow standard ``json.loads`` behavior: the
    last value wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Malformed JSON on line: {!r}".format(line)
            ) from exc
    return values
