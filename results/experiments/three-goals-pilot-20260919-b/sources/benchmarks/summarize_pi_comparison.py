"""Summarize complete Pi task runs without dropping failures or queue time."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(root):
    runs = []
    for name in ['native1', 'engine1', 'engine2', 'native2']:
        folder = root / name
        summary = json.loads((folder / 'summary.json').read_text())
        rows = [json.loads(s) for s in (folder / 'inference.jsonl').read_text().splitlines()]
        traces = [r['trace'] for r in rows if r.get('trace')]
        usage = {key: sum(t['usage'][key] for t in traces)
                 for key in ['prompt_tokens', 'completion_tokens', 'total_tokens']}
        metrics = {key.removesuffix('_ms'): sum(t['metrics'][key] for t in traces) / 1000
                   for key in ['queue_time_ms', 'time_to_first_token_ms', 'generation_time_ms']}
        acceptance = json.loads((folder / 'acceptance.json').read_text())
        runs.append({'run': name, **summary, **usage, 'engine_seconds': metrics,
                     'scheduled_to_last_seconds': metrics['time_to_first_token'] + metrics['generation_time'],
                     'acceptance': acceptance['status'],
                     'source_bytes': sum(f.stat().st_size for f in (folder / 'workspace').glob('*.py')),
                     'traced_requests': len(traces), 'calls_accepted': sum(bool(r.get('call')) for r in rows)})
    means = {}
    for mode in ['native', 'engine']:
        selected = [r for r in runs if r['protocol_mode'] == mode]
        means[mode] = {key: statistics.mean(r[key] for r in selected) for key in
                       ['seconds', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'scheduled_to_last_seconds']}
        means[mode]['queue_seconds'] = statistics.mean(r['engine_seconds']['queue_time'] for r in selected)
        means[mode]['generation_seconds'] = statistics.mean(r['engine_seconds']['generation_time'] for r in selected)
    return {'runs': runs, 'means': means,
            'observed_wall_time_reduction_pct': 100 * (1 - means['engine']['seconds'] / means['native']['seconds']),
            'observed_wall_speed_ratio': means['native']['seconds'] / means['engine']['seconds'],
            'limitation': 'Two runs per mode on shared GPU load, different generated programs and tool trajectories; not causal or stable speedup evidence.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', default='comparison.json')
    args = parser.parse_args()
    result = summarize(args.root)
    with (args.root / args.output).open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'runs'}, ensure_ascii=False, indent=2))
