"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with ``json.loads`` and the
resulting values are returned in line order.  Whitespace-only lines are
skipped.  A final line without a trailing newline is handled, as are CRLF
line endings and Unicode content.

Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse *text* as JSON Lines and return a list of decoded values.

    Blank (whitespace-only) lines are skipped.  Each remaining line is
    decoded with :func:`json.loads`.  If a non-blank line is not valid
    JSON, a :class:`ValueError` is raised.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Invalid JSON on line: {!r}".format(line)
            ) from exc
    return values
