"""Count all requests, including intentional native routing, in a frozen run."""
import argparse
import json
from pathlib import Path


def summarize(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    rows = [json.loads(line) for line in (root / 'rows.jsonl').read_text().splitlines()]
    expected = {(c, n, a) for c in manifest['cases']
                for n in range(manifest['repeats']) for a in manifest['arms']}
    assert len(rows) == len(expected), 'Incomplete or duplicate rows'
    assert {(r['case'], r['repeat'], r['arm']) for r in rows} == expected
    assert all(r['usage_complete'] for r in rows), 'Missing usage'
    result = {}
    for group in ['all', 'supported']:
        result[group] = {}
        for arm in manifest['arms']:
            selected = [r for r in rows if r['arm'] == arm and
                        (group == 'all' or r['case'] != manifest['unsupported_case'])]
            attempts = [a for r in selected for a in r['attempts']]
            totals = {
                'n': len(selected), 'passed': sum(r['passed'] for r in selected),
                'first_attempt_passed': sum(r['attempts'][0]['passed'] for r in selected),
                'native_routes': sum(r['explicit_native_route'] for r in selected),
                'failure_fallbacks': sum(r['failure_fallback'] for r in selected),
                'requests': len(attempts), 'seconds': sum(r['seconds'] for r in selected),
                'usage': {k: sum(r['usage'][k] for r in selected)
                          for k in ['prompt_tokens', 'completion_tokens', 'total_tokens']},
            }
            for metric in ['generation_time_ms', 'queue_time_ms']:
                values = [a.get('metrics', {}).get(metric) for a in attempts]
                totals[metric] = sum(values) if all(v is not None for v in values) else None
            result[group][arm] = totals
    result['limitations'] = 'Seven synthetic tasks, one repetition, shared queue; no stable speed or production claim.'
    with (root / 'summary.json').open('x') as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    summarize(parser.parse_args().root)
