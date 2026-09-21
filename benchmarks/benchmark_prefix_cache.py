"""Single-variable cache-salt probe of the actual fused engine endpoint."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid

from benchmark_tokenizer_preparation import bridge, ROOT


@contextmanager
def backend(out):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with (out / 'ssh-stderr.log').open('w') as log:
        tunnel = subprocess.Popen(['ssh', '-N', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-L', f'127.0.0.1:{port}:127.0.0.1:8000', 'rs-yuesheng-gpu-public'], stderr=log)
        try:
            url = f'http://127.0.0.1:{port}'
            for _ in range(40):
                if tunnel.poll() is not None:
                    raise RuntimeError('SSH tunnel exited')
                try:
                    urllib.request.urlopen(url + '/health', timeout=2).close()
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise RuntimeError('Service unreachable')
            yield url
        finally:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()


def freeze(out):
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (out / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(out)) + '\n' for p in files))


def main(out, snapshot, repeats):
    out = out.resolve()
    out.mkdir(exist_ok=False)
    raw = (snapshot / 'manifest.json').read_bytes()
    schema = {'type': 'object', 'properties': {'content': {'const': 'OK'}}, 'required': ['content'], 'additionalProperties': False}
    tail = [[{'role': 'assistant', 'content': 'A'}, {'role': 'user', 'content': 'Return only {"content":"OK"}. Schema: ' + json.dumps(schema)}]]
    manifest = dict(repeats=repeats, reference_lines=[100, 500, 1000], turns=3, tokenizer=json.loads(raw),
        method='Fused endpoint; random request salt versus stable per-sequence salt. Identical prompts/schemas; '
               'three related turns, first cold and next two warm opportunities; shuffled arm order, three repetitions. '
               'One forced classification label and fixed reply: cache mechanics only, not task quality. '
               'No global cache reset. Token preparation excluded from HTTP timing.')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    for relative in ['deploy/vllm_direct_tools.py', 'deploy/local_tokenizer.py', 'integrations/pijit/bridge.py',
                     'benchmarks/benchmark_prefix_cache.py', 'benchmarks/benchmark_tokenizer_preparation.py']:
        target = out / 'sources' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    rows = []
    rng = random.Random(731)
    try:
        with backend(out) as url:
            os.environ.update(PIJIT_URL=url, PIJIT_LOCAL_TOKENIZER=str(snapshot),
                              PIJIT_TOKENIZER_REVISION=hashlib.sha256(raw).hexdigest())
            os.environ.pop('PIJIT_LOCAL_TOKENIZER_VERIFY', None)
            os.environ.pop('PIJIT_CONTINUATION_CACHE', None)
            caps = json.load(urllib.request.urlopen(url + '/v1/openjev/capabilities'))
            assert caps.get('prefix_cache_version') == 1, caps
            (out / 'capabilities.json').write_text(json.dumps(caps, indent=2))
            label = bridge.tokenize_label('A')
            for lines in manifest['reference_lines']:
                for repeat in range(repeats):
                    nonce = uuid.uuid4().hex
                    prompts = []
                    for turn in range(3):
                        messages = [{'role': 'system', 'content': 'Cache experiment ' + nonce + '. Reference data:\n' +
                                     'def read_text(path): return path.read_text(encoding="utf-8")\n' * lines},
                                    {'role': 'user', 'content': f'Turn {turn}. Select A. The next response must be OK.'}]
                        prefix, suffixes = bridge.continuation_tokens(messages, tail)
                        prompts.append(dict(prompt_ids=prefix, candidate_ids=label, continuations=suffixes,
                                            tools=[dict(name='plan', parameters=schema)], max_tokens=64, plan_budget=True))
                    arms = ['request', 'session']
                    rng.shuffle(arms)
                    for arm in arms:
                        for turn, payload in enumerate(prompts):
                            sent = dict(payload, **({'cache_salt': nonce} if arm == 'session' else {}))
                            started = time.perf_counter()
                            result = bridge.post('/v1/openjev/toolcall', sent)
                            row = dict(lines=lines, repeat=repeat, arm=arm, turn=turn, seconds=time.perf_counter()-started,
                                       prompt_tokens=len(payload['prompt_ids']), payload_sha256=hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
                                       result=result, correct=result['call']=={'name':'plan','arguments':{'content':'OK'}})
                            rows.append(row)
                            (out / 'report.json').write_text(json.dumps(rows, indent=2))
                            assert row['correct'], result
                            print(json.dumps({k:v for k,v in row.items() if k in ['lines','repeat','arm','turn','seconds','prompt_tokens','correct']} |
                                             {'cached':result['decision']['cached_prefix_tokens']}), flush=True)
    finally:
        freeze(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--repeats', type=int, default=3)
    a = p.parse_args()
    main(a.out, a.snapshot.resolve(), a.repeats)
