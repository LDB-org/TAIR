"""Forced selected-candidate continuation probe; no natural routing or Agent timing."""
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
from benchmark_expanded_reuse import wait_backend_idle

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main(out,tokenizer,compact_delta=False):
    out.mkdir(parents=True,exist_ok=False)
    bridge=load('binding_bridge',ROOT/'integrations/pijit/bridge.py')
    old_path=ROOT/'results/experiments/artifact-context-ablation-20260921-a/sources/deploy/tool_plan.py'
    old=load('old_tool_plan',old_path)
    jobs={j['id']:j for j in cases()}
    seed_root=ROOT/'results/experiments/artifact-context-ablation-20260921-a'
    seeds=[(jobs[name],seed_root/(name+'-tair_refs')/'project-after'/jobs[name]['primary_file'])
           for name in ['jsonl_base','unique_base']]
    entries=[dict(id=hashlib.sha256((j['prompt']+'\0'+p.read_text()).encode()).hexdigest(),
                  source=p.read_text(),contract=j['prompt'],verification=bridge.tool_plan.content_evidence([p.name])) for j,p in seeds]
    fixtures=[dict(task='unique_repeat',candidate=1),dict(task='unique_repeat',candidate=0),dict(task='unique_changed',candidate=1)]
    if compact_delta:
        fixtures += [dict(task='jsonl_repeat',candidate=0),dict(task='jsonl_changed',candidate=0)]
    sources={}
    for directory in ['deploy','integrations/pijit','benchmarks']:
        for p in (ROOT/directory).glob('*.py'):
            relative=p.relative_to(ROOT);target=out/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(p.read_bytes());sources[str(relative)]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'legacy_tool_plan.py').write_bytes(old_path.read_bytes())
    manifest=dict(fixtures=fixtures,jobs={f['task']:jobs[f['task']] for f in fixtures},entries=entries,
                  source_sha256=sources,legacy_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
                  method='Forced candidate via a singleton allowed label retaining its original catalog letter. '
                  'Full catalog remains visible. Paired old/new descriptions and continuations; identical schemas. '
                  'Only one write allowed by oracle. No Pi, natural classification, learning, shell execution, or retries.')
    if compact_delta:
        manifest.update(compact_delta=True,method='Forced candidate; current implementation in both arms, identical catalog/schema/full current request. Updated arm replaces only the selected continuation line diff with the existing word diff, falling back to line diff when empty. Independent first-write oracle; not natural routing or full-Agent speed.')
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ['PIJIT_LOCAL_TOKENIZER']=str(tokenizer)
    os.environ['PIJIT_TOKENIZER_REVISION']=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest()
    tools=[dict(name='write',description='Write a text file',parameters=bridge.tool_plan.obj(dict(path=dict(type='string'),content=dict(type='string'))))]
    labels=bridge.LABELS;rows=[]
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    os.environ['PIJIT_URL']=url=f'http://127.0.0.1:{port}'
    with (out/'ssh-stderr.log').open('w') as log:
        tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes',
                                 '-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'],stderr=log)
        try:
            for _ in range(40):
                if tunnel.poll() is not None:raise RuntimeError('Tunnel exited')
                try:
                    if urllib.request.urlopen(url+'/health',timeout=1).status==200:break
                except OSError:time.sleep(.25)
            else:raise RuntimeError('Service unreachable')
            (out/'initial-idle.json').write_text(json.dumps(wait_backend_idle(url)))
            for number,fixture in enumerate(fixtures):
                job=jobs[fixture['task']];candidates=[dict(e,request_delta=bridge.tool_plan.request_delta(e['contract'],job['prompt'])) for e in entries]
                if compact_delta:
                    for entry in candidates:entry['contract_changes']=bridge.tool_plan.contract_changes(entry['contract'],job['prompt'])
                old_options=bridge.tool_plan.branches(tools,candidates) if compact_delta else old.branches(tools,candidates)
                new_options=bridge.tool_plan.branches(tools,candidates)
                assert [o['parameters'] for o in old_options]==[o['parameters'] for o in new_options]
                selected=1+fixture['candidate'];letter=labels[selected]
                for updated in ([False,True] if number%2==0 else [True,False]):
                    module=bridge.tool_plan if updated or compact_delta else old;options=new_options if updated else old_options
                    continuation_candidates=[dict(e,request_delta=e.get('contract_changes') or e['request_delta'])
                                             for e in candidates] if compact_delta and updated else candidates
                    catalog='\n'.join(f'{label}: {option["description"]}' for label,option in zip(labels,options))
                    messages=[dict(role='system',content='Produce exactly one write to the requested file. '
                                   'Reject incompatible stored content by generating a normal write in this same request. '
                                   'No shell tools; an independent oracle runs after the response. Catalog:\n'+catalog),dict(role='user',content=job['prompt'])]
                    bridge.LABELS=letter
                    trace=dict(stage_seconds={},http_requests=[]);token=bridge.TRACE.set(trace);start=time.perf_counter()
                    row=dict(**fixture,updated=updated,forced_label=letter)
                    try:
                        response=bridge.infer(messages,[dict(options[selected],parameters=module.decoder_schema(options[selected]['parameters']))],
                            classification_prompt='Choose the next action from the catalog.',plan_budget=True,
                            branch_instruction=lambda index,option:module.continuation(selected,tools,continuation_candidates,options[selected]))
                        decoded=copy.deepcopy(response);decoded['decision']['index']=selected
                        call,reused=module.decode(decoded,tools,candidates,options)
                        row.update(response=response,call=call,reused=bool(reused),request_seconds=time.perf_counter()-start)
                        steps=call.get('arguments',{}).get('steps',[])
                        row['passed']=False
                        if len(steps)==1 and steps[0]['name']=='write' and steps[0]['arguments']['path']==job['primary_file']:
                            with tempfile.TemporaryDirectory(prefix='tair-binding-oracle-') as temp:
                                Path(temp,job['primary_file']).write_text(steps[0]['arguments']['content'])
                                check=subprocess.run([sys.executable,'-B','-c',job['check']],cwd=temp,capture_output=True,text=True,timeout=15)
                                row.update(passed=check.returncode==0,oracle_stderr=check.stderr)
                    finally:
                        bridge.LABELS=labels;bridge.TRACE.reset(token);row['trace']=trace;rows.append(row)
                        (out/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
                    print(json.dumps({k:v for k,v in row.items() if k not in ['response','call','trace','oracle_stderr']}),flush=True)
            for relative,digest in sources.items():assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest
            (out/'final-idle.json').write_text(json.dumps(wait_backend_idle(url)))
        finally:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
            (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n'
                 for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--tokenizer',type=Path,required=True)
    parser.add_argument('--compact-delta',action='store_true');args=parser.parse_args();main(args.out,args.tokenizer,args.compact_delta)
