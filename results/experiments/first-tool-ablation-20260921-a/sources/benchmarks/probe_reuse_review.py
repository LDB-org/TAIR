"""Forced-candidate component probe; NOT natural selection or complete Agent timing."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from expanded_reuse_cases import cases
from robustness_cases import cases as robustness_cases

ROOT = Path(__file__).resolve().parents[1]


def main(out, tokenizer):
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('probe_bridge', ROOT/'integrations/pijit/bridge.py')
    bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
    jobs = {job['id']: job for job in cases()+robustness_cases()}
    seeds = {
        'totals': 'results/experiments/shortlist-reuse-ablation-20260920-a/totals_base-tair/project-after/totals_base.sql',
        'nullable': 'results/experiments/execution-guidance-expanded-20260920-a/nullable_base-tair/project-after/nullable_base.sql',
    }
    fixtures = []
    for family, path in seeds.items():
        source = (ROOT/path).read_text()
        for phase in ('base', 'changed'):
            job = jobs[family+'_'+phase]
            fixtures.append(dict(job=job, source=source, contract=jobs[family+'_base']['prompt'],
                                 source_path=path, source_sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()))
    source_hashes = {}
    for directory in ('deploy', 'integrations/pijit', 'benchmarks'):
        for path in (ROOT/directory).glob('*.py'):
            relative = path.relative_to(ROOT); target = out/'sources'/relative
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
            source_hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(fixtures=fixtures, source_sha256=source_hashes,
                    method='One forced content candidate; ordinary generation and reply remain legal within that branch. '
                    'No Pi Agent, natural classification, learning, or model-specified shell execution. '
                    'Each result must decode to one write at the requested path and pass the authored SQL oracle. '
                    'No retry. Paired order alternates; existing development tasks, not held-out data.')
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    for key in list(os.environ):
        if key.startswith(('PIJIT_', 'TAIR_')): del os.environ[key]
    os.environ['PIJIT_LOCAL_TOKENIZER'] = str(tokenizer)
    os.environ['PIJIT_TOKENIZER_REVISION'] = hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest()
    tools = [dict(name='write', description='Write a text file', parameters=bridge.tool_plan.obj(dict(
        path=dict(type='string'), content=dict(type='string'))))]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    os.environ['PIJIT_URL'] = url = f'http://127.0.0.1:{port}'
    rows = []
    with (out/'ssh-stderr.log').open('w') as log:
        tunnel = subprocess.Popen(['ssh', '-N', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ExitOnForwardFailure=yes', '-L', f'127.0.0.1:{port}:127.0.0.1:8000',
            'rs-yuesheng-gpu-public'], stderr=log)
        try:
            for _ in range(40):
                if tunnel.poll() is not None: raise RuntimeError('Tunnel exited')
                try:
                    if urllib.request.urlopen(url+'/health', timeout=1).status == 200: break
                except OSError: time.sleep(.25)
            else: raise RuntimeError('Service unreachable')
            from benchmark_expanded_reuse import wait_backend_idle
            manifest['initial_idle'] = wait_backend_idle(url)
            (out/'initial-idle.json').write_text(json.dumps(manifest['initial_idle']))
            for number, fixture in enumerate(fixtures):
                job = fixture['job']
                for review in ((False, True) if number % 2 == 0 else (True, False)):
                    entry = dict(id='fixture', source=fixture['source'], contract=fixture['contract'],
                        request_delta=bridge.tool_plan.request_delta(fixture['contract'], job['prompt']),
                        contract_changes=bridge.tool_plan.contract_changes(fixture['contract'], job['prompt']))
                    options = bridge.tool_plan.branches(tools, [entry], reuse_review=review)
                    selected = options[len(tools)]
                    messages = [dict(role='system', content='This is a component test. Produce exactly one write to the '
                        'requested filename, with content satisfying the current request. No shell tools are available; '
                        'an independent checker runs after this response. Stored content may be incompatible.\n'+selected['description']),
                        dict(role='user', content=job['prompt'])]
                    trace = dict(stage_seconds={}, http_requests=[])
                    token = bridge.TRACE.set(trace); started = time.perf_counter()
                    row = dict(task=job['id'], review=review, expected_compatible=job['id'].endswith('_base'))
                    try:
                        response = bridge.infer(messages, [dict(selected, parameters=bridge.tool_plan.decoder_schema(selected['parameters']))],
                            branch_instruction=lambda index, option: bridge.tool_plan.continuation(len(tools), tools, [entry], selected),
                            plan_budget=True)
                        row.update(response=response, request_seconds=time.perf_counter()-started)
                        decoded = copy.deepcopy(response); decoded['decision']['index'] = len(tools)
                        call, reused = bridge.tool_plan.decode(decoded, tools, [entry], options)
                        row.update(call=call, reused=bool(reused))
                        steps = call.get('arguments', {}).get('steps', [])
                        if len(steps)!=1 or steps[0]['name']!='write' or steps[0]['arguments']['path']!=job['primary_file']:
                            row.update(passed=False, error='Expected one write to the current destination')
                        else:
                            with tempfile.TemporaryDirectory(prefix='tair-review-oracle-') as temp:
                                Path(temp, job['primary_file']).write_text(steps[0]['arguments']['content'])
                                check = subprocess.run([sys.executable, '-B', '-c', job['check']], cwd=temp,
                                    capture_output=True, text=True, timeout=15)
                                row.update(passed=check.returncode==0, oracle_stderr=check.stderr)
                    except Exception as error:
                        row.update(passed=False, error=repr(error))
                        raise
                    finally:
                        bridge.TRACE.reset(token); row['trace']=trace; rows.append(row)
                        (out/'report.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
                    print(json.dumps({k:v for k,v in row.items() if k in ('task','review','passed','reused','request_seconds')}, ensure_ascii=False), flush=True)
            for path, digest in source_hashes.items():
                assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest, path
        finally:
            tunnel.terminate()
            try: tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired: tunnel.kill(); tunnel.wait()
            (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(out))+'\n'
                for path in sorted(out.rglob('*')) if path.is_file() and path.name!='SHA256SUMS'))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tokenizer', type=Path, required=True)
    args=parser.parse_args(); main(args.out.resolve(), args.tokenizer.resolve())
