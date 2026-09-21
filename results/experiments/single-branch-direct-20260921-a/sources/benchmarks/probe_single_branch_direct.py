"""Singleton fused classification versus direct completion, without deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import uuid

from probe_candidate_binding import load
from benchmark_expanded_reuse import wait_backend_idle

ROOT = Path(__file__).resolve().parents[1]


def exact(value):
    if isinstance(value, str):
        return dict(type='string', enum=[value])
    if isinstance(value, list):
        assert len(value) == 1
        return dict(type='array', minItems=1, maxItems=1, items=exact(value[0]))
    return dict(type='object', properties={k:exact(v) for k,v in value.items()},
                required=list(value), additionalProperties=False)


def main(out, tokenizer):
    out.mkdir(parents=True, exist_ok=False)
    for key in list(os.environ):
        if key.startswith(('PIJIT_', 'TAIR_')):
            del os.environ[key]
    os.environ.update(PIJIT_LOCAL_TOKENIZER=str(tokenizer),
        PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest())
    b = load('singleton_bridge', ROOT/'integrations/pijit/bridge.py')
    fixtures = [dict(content='OK'), dict(steps=[dict(name='write', arguments=dict(path='io.py',
        content='from pathlib import Path\n\ndef read(path):\n    return Path(path).read_text()\n\ndef write(path, text):\n    Path(path).write_text(text)\n'))]),
        dict(steps=[dict(name='write', arguments=dict(path='lines.txt',
            content=''.join(f'line {i:04d}\n' for i in range(32))))])]
    manifest = dict(method='Fixed exact-output component comparison, singleton fused endpoint versus standard completion with identical generation prompt/schema. Not new-route acceptance or full-Agent speed.',
        tokenizer_revision=os.environ['PIJIT_TOKENIZER_REVISION'], fixtures=fixtures, source_sha256={})
    for directory in ('deploy', 'integrations/pijit', 'benchmarks'):
        for path in (ROOT/directory).glob('*'):
            if path.suffix not in ('.py', '.ts', '.mjs'):
                continue
            relative=path.relative_to(ROOT); target=out/'sources'/relative
            target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(path.read_bytes())
            manifest['source_sha256'][str(relative)]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'; os.environ['PIJIT_URL']=url
    rows=[]
    with (out/'ssh-stderr.log').open('w') as log:
        tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'],stderr=log)
        try:
            for _ in range(40):
                if tunnel.poll() is not None:raise RuntimeError('Tunnel exited')
                try:
                    if urllib.request.urlopen(url+'/health',timeout=1).status==200:break
                except OSError:time.sleep(.25)
            else:raise RuntimeError('Service unreachable')
            (out/'initial-idle.json').write_text(json.dumps(wait_backend_idle(url)))
            prepared=[]
            for args in fixtures:
                schema=exact(args)
                messages=[dict(role='user',content='Return the specified exact plan. Choose A: plan.')]
                tails=[[dict(role='assistant',content='A'),dict(role='user',content='Generate ONLY JSON. Schema: '+json.dumps(schema))]]
                prefix,suffixes=b.continuation_tokens(messages,tails)
                prepared.append(dict(prompt_ids=prefix,candidate_ids=b.labels(1),continuations=suffixes,
                    tools=[dict(name='plan',parameters=schema)],max_tokens=1024,plan_budget=True))
            (out/'requests.json').write_text(json.dumps(prepared))
            schedule=[(0,-1,'fused'),(0,-1,'direct')]
            for i in range(len(fixtures)):
                for repeat in range(2):
                    schedule.extend((i,repeat,arm) for arm in (['fused','direct'] if repeat==0 else ['direct','fused']))
            for fixture,repeat,arm in schedule:
                body=prepared[fixture]
                route='/v1/openjev/toolcall'
                request=body
                if arm=='direct':
                    route='/v1/completions'
                    request=dict(model='/model',prompt=body['prompt_ids']+body['continuations'][0],
                        temperature=0,max_tokens=1024,return_token_ids=True,cache_salt=uuid.uuid4().hex,
                        structured_outputs=dict(json=body['tools'][0]['parameters']))
                begin=time.perf_counter(); response=b.post(route,request); seconds=time.perf_counter()-begin
                if arm=='direct':
                    choice=response['choices'][0]; assert choice['finish_reason']=='stop'
                    actual=json.loads(choice['text']); generated=response['usage']['completion_tokens']; controls=0
                else:
                    actual=response['call']['arguments']; generated=response['generated_argument_tokens']; controls=response['classification_control_records']
                row=dict(fixture=fixture,repeat=repeat,arm=arm,seconds=seconds,passed=actual==fixtures[fixture],
                    generated_tokens=generated,controls=controls,input_tokens=len(body['prompt_ids'])+len(body['continuations'][0]),response=response)
                rows.append(row); (out/'report.json').write_text(json.dumps(rows,indent=2))
                print(json.dumps({k:v for k,v in row.items() if k!='response'}),flush=True)
                assert row['passed']
            (out/'final-idle.json').write_text(json.dumps(wait_backend_idle(url)))
        finally:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
            (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n'
                for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True); parser.add_argument('--tokenizer',type=Path,required=True)
    args=parser.parse_args(); main(args.out,args.tokenizer)
