"""Paired first-plan probe: classify explicit order without executing generated tools."""
import argparse,hashlib,json,os,random,socket,subprocess,tempfile,time,urllib.request
from pathlib import Path
from probe_candidate_binding import load
from benchmark_expanded_reuse import wait_backend_idle
from continuation_cases import cases
ROOT=Path(__file__).resolve().parents[1]
GUIDANCE='Honor the current user\'s explicit operation order when selecting the FIRST action. Do not insert preliminary reads, searches, or checks before an explicitly requested first operation. '


def main(out,tokenizer):
    out.mkdir(parents=True,exist_ok=False)
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ.update(PIJIT_LOCAL_TOKENIZER=str(tokenizer),PIJIT_PLAN_DISABLE_REUSE='1',
        PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest())
    b=load('order_bridge',ROOT/'integrations/pijit/bridge.py')
    catalog=json.loads((ROOT/'results/experiments/plan-client-profile-20260920-a/catalog.json').read_text())
    repair=cases()[0]
    fixtures=[dict(id='python_check_first',prompt=repair['prompt'],expected=dict(name='bash',arguments=dict(command='python3 check_calc.py'))),
        dict(id='python_read_first',prompt='Read calc.py first, before running any command. Then run python3 check_calc.py. Fix mean to return a float mean, or None on empty input. Preserve check_calc.py and run it after the fix.',expected=dict(name='read',arguments=dict(path='calc.py'))),
        dict(id='javascript_check_first',prompt='Run node check_calc.mjs first, before inspecting files. Then read calc.mjs and fix mean to return the arithmetic mean, or null for empty input. Do not change check_calc.mjs. Run it again after fixing.',expected=dict(name='bash',arguments=dict(command='node check_calc.mjs'))),
        dict(id='javascript_read_first',prompt='Read calc.mjs first, before running any command. Then run node check_calc.mjs. Fix mean to return the arithmetic mean, or null for empty input. Preserve check_calc.mjs and run it after the fix.',expected=dict(name='read',arguments=dict(path='calc.mjs')))]
    sources={}
    for directory in ('deploy','integrations/pijit','benchmarks'):
        for p in (ROOT/directory).glob('*'):
            if p.suffix not in ('.py','.ts','.mjs'):continue
            relative=p.relative_to(ROOT);target=out/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
            sources[str(relative)]=hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(fixtures=fixtures,guidance=GUIDANCE,source_sha256=sources,method='One natural classification and generated plan per arm and fixture; identical empty-book context and schemas; no tool execution, Agent completion, or end-to-end speed claim.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    os.environ['PIJIT_URL']=url=f'http://127.0.0.1:{port}'
    rows=[];original=b.infer;rng=random.Random(731)
    with (out/'ssh-stderr.log').open('w') as log,tempfile.TemporaryDirectory(prefix='tair-order-') as temp:
        tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'],stderr=log)
        try:
            for _ in range(40):
                if tunnel.poll() is not None:raise RuntimeError('Tunnel exited')
                try:
                    if urllib.request.urlopen(url+'/health',timeout=1).status==200:break
                except OSError:time.sleep(.25)
            else:raise RuntimeError('Service unreachable')
            (out/'initial-idle.json').write_text(json.dumps(wait_backend_idle(url)))
            workspace=Path(temp)/'workspace';workspace.mkdir()
            for fixture in fixtures:
                pair=[];arms=[False,True];rng.shuffle(arms)
                for guided in arms:
                    b.STATE=Path(temp)/fixture['id']/str(guided)
                    captured={}
                    def infer(messages,options,**kwargs):
                        if guided:kwargs['classification_prompt']=GUIDANCE+kwargs['classification_prompt']
                        captured.update(messages=messages,options=options,prompt=kwargs['classification_prompt'],tails=[kwargs['branch_instruction'](i,o) for i,o in enumerate(options)])
                        return original(messages,options,**kwargs)
                    b.infer=infer;trace=dict(stage_seconds={},http_requests=[]);token=b.TRACE.set(trace);start=time.perf_counter()
                    try:response=b.generic_plan_chat(dict(cwd=str(workspace),inner_tools=catalog,context=dict(messages=[dict(role='user',content=fixture['prompt'])])))
                    finally:b.TRACE.reset(token)
                    first=next(iter(response['call']['arguments'].get('steps',[])),{})
                    expected=fixture['expected'];args=first.get('arguments',{})
                    matches=first.get('name')==expected['name'] and all(args.get(k)==v for k,v in expected['arguments'].items())
                    row=dict(task=fixture['id'],guided=guided,first_action_matches=matches,first=first,response=response,trace=trace,seconds=time.perf_counter()-start,captured=captured)
                    rows.append(row);pair.append(captured)
                    (out/'report.json').write_text(json.dumps(rows,indent=2))
                    print(json.dumps({k:row[k] for k in ('task','guided','first_action_matches','first','seconds')}),flush=True)
                for key in ('messages','options','tails'):assert pair[0][key]==pair[1][key],key
            (out/'final-idle.json').write_text(json.dumps(wait_backend_idle(url)))
            for relative,digest in sources.items():assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest
        finally:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
            (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--tokenizer',type=Path,required=True);a=p.parse_args();main(a.out,a.tokenizer)
