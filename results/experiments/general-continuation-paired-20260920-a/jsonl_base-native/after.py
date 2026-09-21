"""JSON Lines parsing utilities.

Provides parse_jsonl(text) which decodes a JSON Lines document into a list
of JSON values, in line order.
"""

import json


def parse_jsonl(text):
    """Parse a JSON Lines string into a list of decoded JSON values.

    Each non-blank line is decoded with json.loads and appended to the
    result in line order. Whitespace-only lines are skipped. A final line
    without a trailing newline is handled. Unicode and CRLF line endings
    are supported.

    Args:
        text: The JSON Lines document as a string.

    Returns:
        A list of decoded JSON values, one per non-blank line.

    Raises:
        ValueError: If a non-blank line contains malformed JSON.
    """
    results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Malformed JSON on line {0}: {1}".format(exc.lineno, exc.msg)
            ) from exc
    return results
