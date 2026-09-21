"""Retain rejected generations and failed sessions in Pi protocol accounting."""
import argparse
import json
from pathlib import Path


def summarize(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    waves = [json.loads(line) for line in (root / 'waves.jsonl').read_text().splitlines()]
    assert len(waves) == len(manifest['modes'])
    assert {w['mode'] for w in waves} == set(manifest['modes'])
    result = []
    for wave in waves:
        assert {r['repeat'] for r in wave['rows']} == set(range(manifest['repeats']))
        sessions = []
        for row in wave['rows']:
            directory = root / f"{row['mode']}-{row['repeat']}"
            records = [json.loads(line) for line in (directory / 'inference.jsonl').read_text().splitlines()]
            traces = [r['trace'] for r in records if r.get('trace')]
            assert all(t.get('usage') for t in traces), 'Missing token accounting'
            sessions.append({'repeat': row['repeat'], 'passed': row['passed'],
                             'behavior_passed': row['validation']['passed'],
                             'requests': len(traces), 'local_stop_events': len(records)-len(traces),
                             'rejected_responses': sum(bool(r.get('trace')) and not r.get('call') for r in records),
                             'tool_errors': row['summary'].get('tool_errors'),
                             'seconds': row['summary'].get('seconds'),
                             'usage': {k: sum(t['usage'][k] for t in traces) for k in ['prompt_tokens','completion_tokens','total_tokens']},
                             'generation_seconds': sum(t['metrics']['generation_time_ms'] for t in traces)/1000,
                             'queue_seconds': sum(t['metrics']['queue_time_ms'] for t in traces)/1000})
        result.append({'mode': wave['mode'], 'batch_seconds': wave['seconds'],
                       'passed': sum(s['passed'] for s in sessions), 'sessions': sessions,
                       'usage': {k: sum(s['usage'][k] for s in sessions) for k in ['prompt_tokens','completion_tokens','total_tokens']}})
    with (root / 'accounting.json').open('x') as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    summarize(p.parse_args().root)
