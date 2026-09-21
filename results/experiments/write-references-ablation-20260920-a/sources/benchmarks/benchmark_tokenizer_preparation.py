"""Paired fixed-input preparation timing; no GPU inference or tool execution."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pijit_bridge', ROOT / 'integrations/pijit/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def main(out, snapshot, repeats):
    out = out.resolve()
    out.mkdir(exist_ok=False)
    raw = (snapshot / 'manifest.json').read_bytes()
    revision = hashlib.sha256(raw).hexdigest()
    messages = [
        [{'role': 'system', 'content': 'Use plan to perform the requested work.'},
         {'role': 'user', 'content': 'Write a UTF-8 file reader; preserve blank lines. 请保留空行。'}],
        [{'role': 'system', 'content': 'Historical candidate source:\n' + 'def read(path): return path.read_text()\n' * 500},
         {'role': 'user', 'content': 'Read input.txt before choosing the next action.'}],
        [{'role': 'user', 'content': 'Read input.txt and report its contents.'},
         {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call-a', 'type': 'function',
           'function': {'name': 'plan', 'arguments': '{"steps":[{"name":"read","arguments":{"path":"input.txt"}}]}'}}]},
         {'role': 'tool', 'tool_call_id': 'call-a', 'name': 'plan', 'content': 'PLAN EXECUTION RESULT error=False\n你好\n'},
         {'role': 'user', 'content': 'Choose the next action. Output only a letter.'}],
    ]
    tails = [[{'role': 'assistant', 'content': letter}, {'role': 'user', 'content':
              'Generate JSON for branch ' + letter + '. Schema: ' + json.dumps({'type': 'object',
                  'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                  'required': ['path'], 'additionalProperties': False})}]
             for letter in bridge.LABELS[:15]]
    manifest = dict(snapshot=json.loads(raw), revision=revision, messages=messages, tails=tails,
                    repeats=repeats, seed=731, method='Paired fixed inputs, shuffled order, 15 branches. '
                    'Remote baseline has no label/continuation cache; local uses pinned label cache. '
                    'Local tokenizer object cache cleared each attempt to include loading; Python process/import startup excluded. '
                    'No GPU inference; require exact prompt, continuation and label token equality in every pair.')
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    for relative in ('deploy/local_tokenizer.py', 'integrations/pijit/bridge.py', 'benchmarks/benchmark_tokenizer_preparation.py'):
        target = out / 'sources' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    rng = random.Random(731)
    rows = []
    tunnel = None
    try:
        with tempfile.TemporaryDirectory(prefix='tair-tokenizer-pair-') as state, (out / 'ssh-stderr.log').open('w') as log:
            bridge.STATE = Path(state)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            tunnel = subprocess.Popen(['ssh', '-N', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                '-L', f'127.0.0.1:{port}:127.0.0.1:8000', 'rs-yuesheng-gpu-public'], stderr=log)
            for key in list(os.environ):
                if key.startswith('PIJIT_'):
                    del os.environ[key]
            os.environ['PIJIT_URL'] = f'http://127.0.0.1:{port}'
            for _ in range(40):
                if tunnel.poll() is not None:
                    raise RuntimeError('SSH tunnel exited')
                try:
                    urllib.request.urlopen(os.environ['PIJIT_URL'] + '/health', timeout=2).close()
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise RuntimeError('Service unreachable')
            for repetition in range(repeats):
                for index, context in enumerate(messages):
                    arms = ['remote', 'local']
                    rng.shuffle(arms)
                    results = {}
                    for arm in arms:
                        if tunnel.poll() is not None:
                            raise RuntimeError('SSH tunnel exited')
                        os.environ.pop('PIJIT_LOCAL_TOKENIZER', None)
                        os.environ.pop('PIJIT_TOKENIZER_REVISION', None)
                        if arm == 'local':
                            os.environ.update(PIJIT_LOCAL_TOKENIZER=str(snapshot), PIJIT_TOKENIZER_REVISION=revision)
                        bridge.local_tokenizer._load.cache_clear()
                        trace = {'http_requests': [], 'stage_seconds': {}}
                        token = bridge.TRACE.set(trace)
                        started = time.perf_counter()
                        try:
                            result = bridge.parallel(lambda fn: fn(), [
                                lambda: bridge.prepare_continuations(context, tails), lambda: bridge.labels(len(tails))], max_workers=2)
                        finally:
                            elapsed = time.perf_counter() - started
                            bridge.TRACE.reset(token)
                        results[arm] = result
                        rows.append(dict(repetition=repetition, context=index, arm=arm, seconds=elapsed,
                            payload_sha256=hashlib.sha256(json.dumps(result).encode()).hexdigest(), trace=trace))
                        (out / 'report.json').write_text(json.dumps(rows, indent=2))
                    assert results['local'] == results['remote'], (repetition, index)
                    print(json.dumps({'repetition': repetition, 'context': index, 'equal': True,
                                      'seconds': {r['arm']: r['seconds'] for r in rows[-2:]}}), flush=True)
    finally:
        if tunnel:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()
        files = sorted(p for p in out.rglob('*') if p.is_file())
        (out / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(out)) + '\n' for p in files))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    main(args.out, args.snapshot.resolve(), args.repeats)
