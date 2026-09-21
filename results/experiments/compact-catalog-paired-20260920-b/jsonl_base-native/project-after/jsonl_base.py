"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Blank lines (whitespace-only) are skipped. Lines are processed in order.
"""

import json


def parse_jsonl(text):
    """Parse JSONL text into a list of decoded JSON values, in line order.

    Whitespace-only lines are skipped. A final line without a trailing
    newline is handled. Malformed non-blank JSON lines raise ``ValueError``.

    Args:
        text: The JSONL content as a string.

    Returns:
        A list of decoded JSON values, one per non-blank line, in order.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
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
