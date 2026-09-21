"""Live remote tokenization A/B with identical inputs; does not execute inference."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import statistics

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pijit_bridge', ROOT / 'integrations/pijit/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, args.out / 'benchmark.py')
    shutil.copyfile(spec.origin, args.out / 'bridge.py')
    bridge.STATE = args.out / 'state'
    tools = [{'name': name, 'description': 'Execute ' + name,
              'parameters': {'type': 'object', 'properties': {'content': {'type': 'string'}},
                             'required': ['content'], 'additionalProperties': False}}
             for name in ('read', 'compact_edit', 'set_cli_default', 'reply_user')]
    messages = [{'role': 'system', 'content': 'Select the next tool for this source editing task.'},
                {'role': 'user', 'content': 'Read app.py and change --workers default to 6.\n' +
                 '\n'.join(f'# source context line {i}' for i in range(300))}]
    (args.out / 'input.json').write_text(json.dumps({'messages': messages, 'tools': tools}, indent=2))
    (args.out / 'manifest.json').write_text(json.dumps({
        'kind': 'Live remote tokenizer calls only; inference intercepted, no GPU inference benchmark',
        'repeats': args.repeats, 'seed': args.seed,
        'tokenizer_revision': os.environ.get('PIJIT_TOKENIZER_REVISION'),
        'cache': 'Optimized cache cold for first pair, reused for subsequent pairs',
        'timing': 'generation_preparation includes tokenization HTTP and label cache access',
    }, indent=2))
    original_post = bridge.post
    bodies = []
    def post(route, payload):
        if route == '/v1/openjev/toolcall':
            bodies.append(payload)
            return {'decision': {'index': 0}}
        return original_post(route, payload)
    bridge.post = post
    rows = []
    rng = random.Random(args.seed)
    for repeat in range(args.repeats):
        modes = ['before', 'optimized']
        rng.shuffle(modes)
        for mode in modes:
            os.environ['PIJIT_SERIAL_PREPARATION'] = str(int(mode == 'before'))
            trace = {'stage_seconds': {}, 'http_requests': []}
            token = bridge.TRACE.set(trace)
            try:
                bridge.infer(messages, tools)
            finally:
                bridge.TRACE.reset(token)
            assert bodies[-1] == bodies[0], 'Optimization changed the inference request'
            row = {'repeat': repeat, 'mode': mode, 'order': modes,
                   'request_sha256': hashlib.sha256(json.dumps(bodies[-1], sort_keys=True).encode()).hexdigest(),
                   **trace}
            rows.append(row)
            with (args.out / 'rows.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
    summary = {mode: {
        'median_preparation_seconds': statistics.median(r['stage_seconds']['generation_preparation']
                                                       for r in rows if r['mode'] == mode),
        'tokenize_requests': sum(len(r['http_requests']) for r in rows if r['mode'] == mode),
        'label_cache_hits': sum(r.get('label_cache_hit', False) for r in rows if r['mode'] == mode),
    } for mode in ('before', 'optimized')}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20260918)
    args = parser.parse_args()
    if args.repeats < 1 or not os.environ.get('PIJIT_URL') or not os.environ.get('PIJIT_TOKENIZER_REVISION'):
        parser.error('Positive repeats, PIJIT_URL and PIJIT_TOKENIZER_REVISION required')
    run(args)
