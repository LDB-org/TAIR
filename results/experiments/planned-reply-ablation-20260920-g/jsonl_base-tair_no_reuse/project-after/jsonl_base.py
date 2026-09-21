import json


def parse_jsonl(text):
    """Parse newline-delimited JSON text into a list of decoded values.

    Whitespace-only lines are skipped. Each nonblank line must contain a
    single valid JSON value; otherwise ValueError is raised. Handles Unicode,
    CRLF line endings, and a final line without a trailing newline.
    """
    results = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        results.append(json.loads(line))
    return results
