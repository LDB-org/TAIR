"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with ``json.loads`` and the
decoded values are returned in line order.  Blank lines (containing only
whitespace) are skipped.  Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.  A
    final line without a trailing newline is handled.  Unicode and CRLF
    line endings are supported.  A non-blank line that is not valid JSON
    raises ``ValueError``.  Duplicate object keys follow ``json.loads``
    semantics (the last value wins).
    """
    values = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        values.append(json.loads(line))
    return values
