"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with ``json.loads`` and the
decoded values are returned in line order.  Whitespace-only lines are
skipped.  A final line without a trailing newline is handled, as are
CRLF line endings and Unicode content.

Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order.  Whitespace-only lines are skipped.
    Each remaining line must contain a single valid JSON document;
    otherwise a ``ValueError`` is raised.

    Duplicate object keys follow ``json.loads`` semantics: the last
    value for a given key wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values.append(json.loads(line))
    return values
