"""Create exact-content long-output tasks; independent of model answers."""
import argparse
import json
from pathlib import Path


CODE = '''"""Summarize CSV transactions using only the Python standard library."""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path


def read_transactions(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"category", "amount"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires category and amount columns")
        for number, row in enumerate(reader, start=2):
            category = row["category"].strip()
            if not category:
                raise ValueError(f"Empty category at line {number}")
            try:
                amount = Decimal(row["amount"])
            except InvalidOperation as error:
                raise ValueError(f"Invalid amount at line {number}") from error
            if not amount.is_finite():
                raise ValueError(f"Non-finite amount at line {number}")
            yield category, amount


def summarize(rows):
    totals = {}
    counts = {}
    for category, amount in rows:
        totals[category] = totals.get(category, Decimal("0")) + amount
        counts[category] = counts.get(category, 0) + 1
    return [
        {
            "category": category,
            "count": counts[category],
            "total": str(totals[category].quantize(Decimal("0.01"))),
        }
        for category in sorted(totals)
    ]


def render_report(summary):
    lines = ["Category | Count | Total", "--- | ---: | ---:"]
    for item in summary:
        category = item["category"].replace("|", "\\\\|")
        lines.append(f"{category} | {item['count']} | {item['total']}")
    return "\\n".join(lines) + "\\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()
    summary = summarize(read_transactions(args.csv_path))
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_report(summary), end="")


if __name__ == "__main__":
    main()
'''


def build():
    # Source is fixed before inference; exact matching detects newline/indent errors.
    write = ('write', 'Use write to create report.py. Copy the source between the markers exactly, including indentation and the final newline. Do not run it.\nBEGIN_SOURCE\n'+CODE+'END_SOURCE',
             {'path': 'report.py', 'content': CODE})
    old = 'SERVICES = {\n'+''.join(
        f'    "worker_{i:02d}": {{"port": {8100+i}, "timeout": 10, "enabled": False}},\n' for i in range(16))+'}\n'
    new = 'SERVICES = {\n'+''.join(
        f'    "worker_{i:02d}": {{"port": {9100+i}, "timeout": 30, "enabled": True}},\n' for i in range(16))+'}\n'
    edit = ('edit', 'Use edit on config.py with exactly one replacement. The oldText and newText must match the marked blocks exactly, including final newlines.\nBEGIN_OLD\n'+old+'END_OLD\nBEGIN_NEW\n'+new+'END_NEW',
            {'path': 'config.py', 'edits': [{'oldText': old, 'newText': new}]})
    content = '\n'.join(f'{i:02d}. Batch {i:02d}: received {i*7} records; accepted {i*7-2}; rejected 2. Preserve the original evidence and check the next batch.' for i in range(1, 37))+'\n'
    reply = ('reply_user', 'Send exactly the report between the markers to the user. Preserve every line and the final newline. Do not summarize or add Markdown fences.\nBEGIN_REPORT\n'+content+'END_REPORT',
             {'content': content})
    return [write, edit, reply]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    a.output.open('x').write(json.dumps(build(), ensure_ascii=False, indent=2))
