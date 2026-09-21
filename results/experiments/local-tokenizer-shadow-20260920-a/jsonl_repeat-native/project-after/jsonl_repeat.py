"""Parse JSON Lines (JSONL) text into a list of decoded JSON values.

Each non-blank line is parsed independently with :func:`json.loads`.
Whitespace-only lines are skipped. Lines are processed in order, so the
returned list preserves the order of the non-blank lines in the input.
"""

import json


def parse_jsonl(text):
    """Parse JSONL ``text`` and return a list of decoded JSON values.

    Args:
        text: A string containing zero or more JSON values, one per line.

    Returns:
        A list of the decoded JSON values, in line order. Whitespace-only
        lines are skipped.

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
                "Malformed JSON on line {0}: {1}".format(
                    exc.lineno, exc.msg
                )
            ) from exc
    return values
