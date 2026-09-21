"""Count correct-call throughput and complete costs without hiding bad outputs."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    rows = [json.loads(line) for line in (root / 'rows.jsonl').read_text().splitlines()]
    waves = [json.loads(line) for line in (root / 'waves.jsonl').read_text().splitlines()]
    expected = {(mode, concurrency, case, repeat) for mode, concurrency in manifest['configurations']
                for case in manifest['cases'] for repeat in range(manifest['repeats'])}
    assert len(rows) == len(expected)
    assert {(r['mode'], r['concurrency'], r['case'], r['repeat']) for r in rows} == expected
    assert len(waves) == len(manifest['configurations'])
    result = []
    for wave in waves:
        selected = [r for r in rows if (r['mode'], r['concurrency']) == (wave['mode'], wave['concurrency'])]
        traces = [r['result'].get('trace', {}) for r in selected]
        complete_usage = all(t.get('usage') for t in traces)
        correct = sum(r['correct'] for r in selected)
        row = {**wave, 'correct': correct, 'completed_requests_per_second': len(selected) / wave['seconds'],
               'correct_calls_per_second': correct / wave['seconds'],
               'median_request_seconds': statistics.median(r['seconds'] for r in selected),
               'max_request_seconds': max(r['seconds'] for r in selected),
               'usage_complete': complete_usage,
               'usage': {k: sum(t['usage'][k] for t in traces) for k in
                         ['prompt_tokens', 'completion_tokens', 'total_tokens']} if complete_usage else None}
        for key in ['generation_time_ms', 'queue_time_ms', 'mean_itl_ms']:
            values = [t.get('metrics', {}).get(key) for t in traces]
            row[key] = (statistics.median(values) if key == 'mean_itl_ms' else sum(values)) if all(v is not None for v in values) else None
        row['cases'] = {case: {'correct': sum(r['correct'] for r in selected if r['case'] == case),
                              'generation_ms': [r['result'].get('trace', {}).get('metrics', {}).get('generation_time_ms')
                                                for r in selected if r['case'] == case]}
                        for case in manifest['cases']}
        result.append(row)
    with (root / 'summary.json').open('x') as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    summarize(parser.parse_args().root)
