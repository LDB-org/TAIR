"""Read-only routing and tool-call counts for paired planner-efficiency experiments."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def analyze(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    configs = manifest['configurations']
    on, off = configs['hybrid'], configs['hybrid_unoptimized']
    assert {k for k in on.keys() | off.keys() if on.get(k) != off.get(k)} == {'PIJIT_PLANNER_EFFICIENCY'}
    assert on['PIJIT_PLANNER_EFFICIENCY'] == '1' and off['PIJIT_PLANNER_EFFICIENCY'] == '0'
    rows = [json.loads(line) for line in (folder / 'rows.jsonl').read_text().splitlines()]
    results = []
    for row in rows:
        counts = Counter()
        roots = 0
        path = folder / f"{row['repeat']}-{row['case']}-{row['arm']}-{row['round']}"
        for line in (path / 'events.jsonl').read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') != 'tool_execution_start':
                continue
            counts[event['toolName']] += 1
            command = event.get('args', {}).get('command', '')
            roots += bool(re.search(r'(?:^|[;&|])\s*find\s+/\s', command))
        routes = [m for m in row['metrics'] if m.get('local_route') == 'explicit_initial_read']
        assert all(m['accounting']['inference_requests'] == 0 for m in routes)
        results.append({k: row[k] for k in ['arm', 'case', 'round', 'repeat', 'passed']} |
                       dict(tools=dict(counts), root_find_starts=roots, explicit_read_routes=len(routes)))
    summaries = {}
    for arm in manifest['arms']:
        selected = [r for r in results if r['arm'] == arm]
        counts = Counter()
        for row in selected:
            counts.update(row['tools'])
        summaries[arm] = dict(tool_calls=dict(counts), root_find_starts=sum(r['root_find_starts'] for r in selected),
                              explicit_read_routes=sum(r['explicit_read_routes'] for r in selected))
    return dict(summaries=summaries, tasks=results,
                limitations='Counts tool starts, including interrupted commands. Root-find detection covers direct shell find / syntax, not every possible filesystem traversal. Bash calls are not automatically redundant: failures and distinct requirements can justify repeated checks. No commands are executed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.folder)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result['summaries'], indent=2))
