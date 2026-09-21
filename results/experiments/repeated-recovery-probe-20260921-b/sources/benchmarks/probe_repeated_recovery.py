"""Paired single-recovery-turn replay of a recorded repeated-error history."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
from probe_candidate_binding import load
from benchmark_expanded_reuse import wait_backend_idle

ROOT=Path(__file__).resolve().parents[1]


def main(out,tokenizer):
    out.mkdir(parents=True,exist_ok=False)
    b=load('recovery_bridge',ROOT/'integrations/pijit/bridge.py')
    prior=ROOT/'results/experiments/parallel-capabilities-ablation-20260921-a'
    old=load('old_recovery_bridge',prior/'sources/integrations/pijit/bridge.py')
    current=b.latest_plan_result
    events=[json.loads(x) for x in (prior/'unique_changed-tair_parallel_caps/events.jsonl').read_text().splitlines()]
    messages=[e['message'] for e in events if e.get('type')=='message_end']
    catalog=json.loads((ROOT/'results/experiments/plan-client-profile-20260920-a/catalog.json').read_text())
    original=next(m for m in messages if m['role']=='assistant')['content'][0]['arguments']['steps'][0]['arguments']['content']
    old_cwd='/private/var/folders/yw/fbsfvfm95956m4m6yfd49z_c0000gn/T/tair-expanded-project-hcosxbfw/workspace'
    package=Path('/tmp/tair-pi-0.85.1/node_modules/@earendil-works/pi-coding-agent')
    assert json.loads((package/'package.json').read_text())['version']=='0.85.1'
    for directory in ['deploy','integrations/pijit','benchmarks']:
        for p in (ROOT/directory).glob('*.py'):
            target=out/'sources'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    (out/'legacy_bridge.py').write_bytes((prior/'sources/integrations/pijit/bridge.py').read_bytes())
    (out/'manifest.json').write_text(json.dumps(dict(source_experiment=prior.name,cuts=[3,4],
        path_rebinding='Both macOS aliases rebound; historical missing-module errors replaced with an actual error produced in the replay workspace.',
        method='One recovery request per arm at frozen history cuts after 3 or 4 failed plans. Only latest-result suffix differs. Native Pi executes returned steps once. No followup turns. Controlled replay, not full Agent speed.',
        model=b.MODEL,pi_version='0.85.1',tokenizer_manifest=json.loads((tokenizer/'manifest.json').read_text())),indent=2))
    for key in list(os.environ):
        if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
    os.environ.update(PIJIT_LOCAL_TOKENIZER=str(tokenizer),PIJIT_TOKENIZER_REVISION=hashlib.sha256((tokenizer/'manifest.json').read_bytes()).hexdigest(),PIJIT_PLAN_DISABLE_REUSE='1')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    os.environ['PIJIT_URL']=url=f'http://127.0.0.1:{port}'
    rows=[]
    with (out/'ssh-stderr.log').open('w') as log,tempfile.TemporaryDirectory(prefix='tair-recovery-replay-') as temp:
        tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'],stderr=log)
        try:
            for _ in range(40):
                if tunnel.poll() is not None:raise RuntimeError('SSH exited')
                try:
                    if urllib.request.urlopen(url+'/health',timeout=1).status==200:break
                except OSError:time.sleep(.25)
            else:raise RuntimeError('No health response')
            (out/'initial-idle.json').write_text(json.dumps(wait_backend_idle(url)))
            project=Path(temp).resolve()/'workspace';project.mkdir();b.STATE=Path(temp)/'state'
            check=Path(temp).resolve()/'unique_test.mjs'
            (project/'unique_changed.mjs').write_text(original)
            check.write_text("import {uniqueStrings} from './unique_changed.mjs'; console.log(uniqueStrings(['a','A']));\n")
            missing=subprocess.run(['node',str(check)],cwd=project,capture_output=True,text=True,timeout=10)
            assert missing.returncode!=0 and 'ERR_MODULE_NOT_FOUND' in missing.stderr
            module_error=missing.stderr+'\n\n\nCommand exited with code 1'
            for cut in [3,4]:
                history=[];failures=0
                for m in messages:
                    history.append(m)
                    failures+=m['role']=='toolResult' and m.get('isError',False)
                    if failures==cut:break
                encoded=json.dumps(history).replace(old_cwd,str(project)).replace(old_cwd.removeprefix('/private'),str(project)).replace('/private/tmp/unique_test.mjs',str(check)).replace('/tmp/unique_test.mjs',str(check)).replace('/private/tmp/unique_changed.mjs',str(Path(temp)/'unique_changed.mjs'))
                history=json.loads(encoded)
                for message in history:
                    if message['role']!='toolResult':continue
                    for block in message.get('content',[]):
                        if block.get('type')!='text':continue
                        result=json.loads(block['text'])
                        if 'ERR_MODULE_NOT_FOUND' in result.get('error',''):
                            result['error']=module_error
                            block['text']=json.dumps(result)
                assert 'tair-expanded-project-hcosxbfw' not in json.dumps(history)
                (out/f'history-{cut}.json').write_text(json.dumps(history,indent=2))
                for updated in ([False,True] if cut==3 else [True,False]):
                    for p in project.iterdir():
                        if p.is_file():p.unlink()
                    (project/'unique_changed.mjs').write_text(original)
                    check.write_text("import {uniqueStrings} from './unique_changed.mjs'; console.log(uniqueStrings(['a','A']));\n")
                    b.latest_plan_result=current if updated else old.latest_plan_result
                    trace=dict(stage_seconds={},http_requests=[]);token=b.TRACE.set(trace);start=time.perf_counter()
                    try:response=b.generic_plan_chat(dict(cwd=str(project),inner_tools=catalog,context=dict(messages=history)))
                    finally:b.TRACE.reset(token)
                    row=dict(cut=cut,updated=updated,inference_seconds=time.perf_counter()-start,response=response,trace=trace)
                    call=response['call'];steps=call.get('arguments',{}).get('steps',[])
                    script='''import * as pi from PACKAGE;
const factories={read:pi.createReadTool,write:pi.createWriteTool,edit:pi.createEditTool,bash:pi.createBashTool,grep:pi.createGrepTool,find:pi.createFindTool,ls:pi.createLsTool};
const results=[];for (const step of STEPS) {try {results.push({name:step.name,result:await factories[step.name](CWD).execute('probe',step.arguments)});}catch(error){results.push({name:step.name,error:String(error)});break;}}
console.log(JSON.stringify(results));'''.replace('PACKAGE',json.dumps((package/'dist/index.js').as_uri())).replace('STEPS',json.dumps(steps)).replace('CWD',json.dumps(str(project)))
                    executed=subprocess.run(['node','--input-type=module','-e',script],cwd=project,capture_output=True,text=True,timeout=45)
                    result=json.loads(executed.stdout) if executed.returncode==0 else []
                    row.update(execution=result,execution_stderr=executed.stderr,all_steps_succeeded=bool(steps) and len(result)==len(steps) and all('error' not in r for r in result))
                    output='\n'.join(c.get('text','') for r in result if r['name']=='bash' for c in r.get('result',{}).get('content',[]))
                    row['expected_checks_observed']=all(s in output for s in ['["Apple","banana","cherry","  Cherry  "]','empty: []','mixed: ["a","b"]'])
                    row['passed']=row['all_steps_succeeded'] and row['expected_checks_observed'] and (project/'unique_changed.mjs').read_text()==original
                    rows.append(row);(out/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
                    print(json.dumps({k:row[k] for k in ['cut','updated','inference_seconds','all_steps_succeeded','expected_checks_observed','passed']}),flush=True)
            (out/'final-idle.json').write_text(json.dumps(wait_backend_idle(url)))
        finally:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
    files=sorted(p for p in out.rglob('*') if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--tokenizer',type=Path,required=True)
    a=p.parse_args();main(a.out.resolve(),a.tokenizer.resolve())
