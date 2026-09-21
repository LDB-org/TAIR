"""Summarize all three arms, retaining failed attempts and fallback costs."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(root):
    rows = [json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()]
    manifest = json.loads((root/'manifest.json').read_text())
    expected = {(c, r, a) for c in manifest['cases'] for r in range(manifest['repeats']) for a in manifest['arms']}
    assert len(rows) == len(expected)
    assert {(r['case'], r['repeat'], r['arm']) for r in rows} == expected
    assert all(r['usage_complete'] for r in rows), 'Missing usage; cannot claim token savings'
    summary = {}
    for arm in manifest['arms']:
        group = [r for r in rows if r['arm'] == arm]
        attempts = [a for r in group for a in r['attempts']]
        controls = sum(a.get('control_records', 0) for a in attempts)
        usage = {k: sum(r['usage'][k] for r in group) for k in ['prompt_tokens', 'completion_tokens', 'total_tokens']}
        summary[arm] = {'tasks': len(group), 'first_pass': sum(r['first_passed'] for r in group),
                        'final_pass': sum(r['passed'] for r in group), 'requests': len(attempts),
                        'fallbacks': len(attempts)-len(group), 'usage': usage,
                        'generated_tokens_excluding_controls': usage['completion_tokens']-controls,
                        'control_records': controls, 'wall_seconds': sum(r['seconds'] for r in group),
                        'median_seconds': statistics.median(r['seconds'] for r in group),
                        'failed_attempts': [{'case': r['case'], 'repeat': r['repeat'], 'error': a.get('error'),
                                             'validation': a.get('validation')} for r in group for a in r['attempts'] if not a['passed']]}
        for key in ['queue_time_ms', 'generation_time_ms']:
            values = [(a.get('metrics') or {}).get(key) for a in attempts]
            summary[arm][key] = sum(values) if all(v is not None for v in values) else None
    summary['combined_reductions'] = {arm: {
        **{k: 1-summary['combined']['usage'][k]/summary[arm]['usage'][k] for k in summary[arm]['usage']},
        'wall_seconds': 1-summary['combined']['wall_seconds']/summary[arm]['wall_seconds']}
        for arm in ['native', 'typed']}
    summary['limitations'] = 'Previously tuned same-project regression; shared backend; task-test oracle fallback; preparation excluded; not a full Pi agent loop or stable speed/production proof.'
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    a = p.parse_args()
    result = summarize(a.root)
    with (a.root/'summary.json').open('x') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
