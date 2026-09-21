"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Whitespace-only lines are skipped. A final line without a trailing
newline is handled. Malformed non-blank JSON lines raise ``ValueError``.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Lines are processed in order. Whitespace-only lines are skipped.
    A final line without a trailing newline is still parsed. Any
    non-blank line that is not valid JSON raises ``ValueError``.

    Duplicate object keys follow :func:`json.loads` behavior: the last
    value wins.
    """
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Invalid JSON on line {0}: {1}".format(exc.lineno, exc.msg)
            ) from exc
    return values
