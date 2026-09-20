"""Real Pi generic plan: JS creation/reuse and read-dependent JSON editing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    for relative in ['deploy/tool_plan.py','deploy/plan_book.py','integrations/pijit/bridge.py',
                     'integrations/pijit/extension.ts','integrations/pijit/plan_executor.mjs',
                     'integrations/pijit/launch.mjs','benchmarks/benchmark_generic_plan.py']:
        target=out/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    with tempfile.TemporaryDirectory(prefix='tair-generic-plan-') as temp:
        root=Path(temp);workspace=root/'workspace';workspace.mkdir()
        (workspace/'settings.json').write_text('{"workers":2,"label":"preserve me"}\n')
        env={k:v for k,v in os.environ.items() if not k.startswith(('PIJIT_','TAIR_'))}
        env.update(PIJIT_SSH_HOST='rs-yuesheng-gpu-public',PIJIT_PYTHON=sys.executable,PIJIT_STATE_DIR=str(root/'state'))
        jobs=[('cold','Create constants.mjs containing exactly "export const answer = 42;" followed by one newline. Then run node --check constants.mjs via bash. Do not create any other file.'),
              ('warm','Create again.mjs containing exactly "export const answer = 42;" followed by one newline. Then run node --check again.mjs via bash. Do not create any other file.'),
              ('edit','Read settings.json. Change only workers to 7, preserve label and all other fields. Run a bash command using python3 to parse the JSON and assert workers is 7 and label is "preserve me". Do not create any other file.')]
        rows=[];previous=0
        try:
            for name,prompt in jobs:
                start=time.perf_counter()
                done=subprocess.run(['node',str(ROOT/'integrations/pijit/launch.mjs'),'--plan-only','-p',prompt],cwd=workspace,
                                    env=env,capture_output=True,text=True,timeout=120)
                seconds=time.perf_counter()-start
                (out/f'{name}-stdout.txt').write_text(done.stdout);(out/f'{name}-stderr.txt').write_text(done.stderr)
                metrics_path=next((root/'state').glob('workspaces/*/metrics.jsonl'))
                all_records=[json.loads(line) for line in metrics_path.read_text().splitlines()]
                records=all_records[previous:];previous=len(all_records)
                row=dict(name=name,seconds=seconds,returncode=done.returncode,records=records)
                rows.append(row);(out/'report.json').write_text(json.dumps(rows,indent=2))
                assert done.returncode==0,done.stderr
                chats=[r for r in records if r['action']=='chat']
                assert chats and all(r.get('generic_plan') and r['available_tools']==['plan'] for r in chats)
                assert all(r['action'] in ('chat','tool_plan_complete') for r in records)
                assert all(r['status']=='ok' for r in records)
                actions=[n for r in records for n in r.get('executed_tools',[])]
                if name in ('cold','warm'):
                    file='constants.mjs' if name=='cold' else 'again.mjs'
                    assert (workspace/file).read_text()=='export const answer = 42;\n'
                    assert 'write' in actions and 'bash' in actions
                    if name=='warm':assert any(r.get('reused_content_ids') for r in chats),'Warm task did not reuse'
                else:
                    assert json.loads((workspace/'settings.json').read_text())==dict(workers=7,label='preserve me')
                    assert 'read' in actions and 'bash' in actions and ('edit' in actions or 'write' in actions)
                    assert len([r for r in chats if r.get('plan_step_names')])>=2
                print(json.dumps(dict(name=name,seconds=seconds,actions=actions,passed=True)),flush=True)
            assert {p.name for p in workspace.iterdir()}=={'settings.json','constants.mjs','again.mjs'}
        finally:
            for path in workspace.iterdir():
                if path.is_file():shutil.copyfile(path,out/path.name)
            for path in (root/'state/agent/sessions').rglob('*.jsonl'):shutil.copyfile(path,out/('session-'+path.name))
            files=sorted(p for p in out.rglob('*') if p.is_file())
            (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
