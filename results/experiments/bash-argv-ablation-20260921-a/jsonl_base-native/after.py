"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with the standard library
``json`` module. Blank lines (whitespace-only) are skipped. Malformed
non-blank lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order. Whitespace-only lines are skipped.
    A final line without a trailing newline is handled. CRLF line
    endings are supported. Malformed non-blank lines raise
    ``ValueError``.
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
