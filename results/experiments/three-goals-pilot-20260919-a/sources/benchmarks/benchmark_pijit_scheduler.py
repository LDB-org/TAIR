"""Bounded retained-KV engine bursts with an identical, exactly checked tool call."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pijit_bridge', ROOT / 'integrations/pijit/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def payload():
    captured = []
    original = bridge.post
    def post(route, body):
        if route == '/v1/openjev/toolcall':
            captured.append(body)
            return {'decision': {'index': 0}}
        return original(route, body)
    bridge.post = post
    try:
        bridge.infer([{'role': 'user', 'content': 'Reply DONE using reply_user.'}], [{
            'name': 'reply_user', 'description': 'Reply to the user.',
            'parameters': {'type': 'object', 'properties': {'content': {'type': 'string', 'enum': ['DONE']}},
                           'required': ['content'], 'additionalProperties': False}}])
    finally:
        bridge.post = original
    return dict(captured[0], max_tokens=64)


def request(body):
    trace = {'http_requests': [], 'stage_seconds': {}}
    token = bridge.TRACE.set(trace)
    started = time.perf_counter()
    try:
        result = bridge.post('/v1/openjev/toolcall', body)
        result['correct'] = result.get('call') == {'name': 'reply_user', 'arguments': {'content': 'DONE'}}
    except Exception as error:
        result = {'correct': False, 'error': type(error).__name__ + ': ' + str(error)}
    finally:
        bridge.TRACE.reset(token)
    return dict(result, client_seconds=time.perf_counter() - started, trace=trace)


def gauge():
    with urllib.request.urlopen(os.environ['PIJIT_URL'].rstrip('/') + '/metrics', timeout=10) as stream:
        lines = stream.read().decode().splitlines()
    return [l for l in lines if any(l.startswith('vllm:' + n + '{') for n in (
        'num_requests_running', 'num_requests_waiting', 'kv_cache_usage_perc'))]


def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, args.out / 'benchmark.py')
    shutil.copyfile(spec.origin, args.out / 'bridge.py')
    body = json.loads(args.payload.read_text()) if args.payload else payload()
    (args.out / 'payload.json').write_text(json.dumps(body, indent=2))
    (args.out / 'manifest.json').write_text(json.dumps({
        'concurrency': args.concurrency, 'requests_per_batch': args.requests,
        'repeats': args.repeats, 'seed': args.seed,
        'payload_sha256': hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
        'timing': 'Client HTTP through complete response; tokenization excluded. One separately recorded warm-up.',
        'scope': 'Single forced tool with exact DONE argument; not a full Agent quality or throughput benchmark.',
        'cache': 'Server assigns a fresh cache salt per request. No client retry. Shared backend traffic remains.'}, indent=2))
    warmup = request(body)
    (args.out / 'warmup.json').write_text(json.dumps(warmup, indent=2))
    if not warmup['correct']:
        return False
    order = [(repeat, concurrency) for repeat in range(args.repeats) for concurrency in args.concurrency]
    random.Random(args.seed).shuffle(order)
    rows = []
    for repeat, concurrency in order:
        before = gauge()
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            responses = list(pool.map(request, [body] * args.requests))
        row = {'repeat': repeat, 'concurrency': concurrency, 'wall_seconds': time.perf_counter() - started,
               'load_before': before, 'load_after': gauge(), 'responses': responses}
        rows.append(row)
        with (args.out / 'rows.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')
        print(json.dumps({k: v for k, v in row.items() if k not in ('responses', 'load_before', 'load_after')}), flush=True)
    summary = {}
    for concurrency in args.concurrency:
        batches = [r for r in rows if r['concurrency'] == concurrency]
        responses = [r for b in batches for r in b['responses']]
        seconds = sum(b['wall_seconds'] for b in batches)
        summary[concurrency] = {
            'requests': len(responses), 'correct': sum(r['correct'] for r in responses),
            'batch_wall_seconds': seconds, 'correct_calls_per_second': sum(r['correct'] for r in responses) / seconds,
            'median_client_seconds': statistics.median(r['client_seconds'] for r in responses),
            'known_generated_tokens': sum(r.get('generated_argument_tokens', 0) for r in responses),
            'known_controls': sum(r.get('classification_control_records', 0) for r in responses),
            'unknown_usage_requests': sum(not h['usage_complete'] for r in responses for h in r['trace']['http_requests']),
        }
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return all(r['correct'] for b in rows for r in b['responses'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--requests', type=int, default=8)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--concurrency', type=int, nargs='+', default=[4, 8])
    parser.add_argument('--seed', type=int, default=20260918)
    args = parser.parse_args()
    if not os.environ.get('PIJIT_URL') or args.requests < 1 or args.repeats < 1 or any(c < 1 or c > 8 for c in args.concurrency):
        parser.error('URL, positive requests/repeats, and concurrency in 1..8 required')
    raise SystemExit(0 if run(args) else 1)
