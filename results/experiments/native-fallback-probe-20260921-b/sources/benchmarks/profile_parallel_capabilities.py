"""Measure real capability GET overlapping local preparation; never run inference."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import socket
import statistics
import subprocess
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main(out, tokenizer, samples):
    if samples<2:raise ValueError('Need at least two paired samples')
    out.mkdir(parents=True,exist_ok=False)
    for name in ['integrations/pijit/bridge.py','deploy/tool_plan.py','deploy/local_tokenizer.py',
                 'benchmarks/profile_parallel_capabilities.py']:
        target=out/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    catalog_path=ROOT/'results/experiments/plan-client-profile-20260920-a/catalog.json'
    catalog=json.loads(catalog_path.read_text())
    (out/'catalog.json').write_bytes(catalog_path.read_bytes())
    manifest=dict(samples=samples,inference_requests=0,pi_version='0.85.1',
        tokenizer_manifest=json.loads((tokenizer/'manifest.json').read_text()),
        method='Real capability GET each call; pinned local tokenizer; mocked inference result; identical request payload hashes required. First pair reported separately. Not end-to-end GPU speed.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ.update(PIJIT_LOCAL_TOKENIZER=str(tokenizer),
        PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest(),
        PIJIT_PLAN_DISABLE_REUSE='1')
    spec=importlib.util.spec_from_file_location('bridge',ROOT/'integrations/pijit/bridge.py')
    b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
    captured=[]
    def post(route,payload):
        assert route=='/v1/openjev/toolcall', 'No inference or remote tokenization permitted'
        captured.append(hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest())
        return dict(decision=dict(index=len(payload['tools'])-1),same_engine_session=True,finish_reason='stop',
                    classification_control_records=1,call=dict(name='plan',arguments=dict(content='probe')))
    b.post=post
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}';os.environ['PIJIT_URL']=url
    rows=[]
    with (out/'ssh-stderr.log').open('w') as log, tempfile.TemporaryDirectory() as temp:
        tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','ConnectTimeout=10','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000',
            'rs-yuesheng-gpu-public'],stderr=log)
        try:
            for _ in range(40):
                if tunnel.poll() is not None:raise RuntimeError('SSH tunnel exited')
                try:
                    if urllib.request.urlopen(url+'/health',timeout=1).status==200:break
                except OSError:time.sleep(.25)
            else:raise RuntimeError('Backend unreachable')
            project=Path(temp)/'project';project.mkdir();b.STATE=Path(temp)/'state'
            payload=dict(cwd=str(project),inner_tools=catalog,context=dict(messages=[dict(role='user',content='Create a Python JSONL parser and check invalid lines.')]))
            rng=random.Random(731)
            for pair in range(samples+1):
                order=[False,True];rng.shuffle(order)
                for enabled in order:
                    os.environ['PIJIT_PARALLEL_CAPABILITIES']='1' if enabled else '0'
                    trace=dict(stage_seconds={},http_requests=[]);token=b.TRACE.set(trace)
                    start=time.perf_counter()
                    try:result=b.generic_plan_chat(payload)
                    finally:b.TRACE.reset(token)
                    rows.append(dict(pair=pair,parallel=enabled,seconds=time.perf_counter()-start,
                        payload_sha256=captured[-1],budget_supported=result['plan_budget_supported'],trace=trace))
            assert len(set(captured))==1, 'Optimization changed inference payload'
            summary={str(enabled):dict(median_seconds=statistics.median(r['seconds'] for r in rows if r['parallel']==enabled and r['pair']>0),
                first_seconds=next(r['seconds'] for r in rows if r['parallel']==enabled)) for enabled in [False,True]}
            (out/'report.json').write_text(json.dumps(dict(rows=rows,summary=summary,identical_payloads=True,inference_requests=0),indent=2))
            print(json.dumps(summary))
        finally:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
    files=sorted(p for p in out.rglob('*') if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tokenizer',type=Path,required=True)
    p.add_argument('--samples',type=int,default=10)
    a=p.parse_args();main(a.out.resolve(),a.tokenizer.resolve(),a.samples)
