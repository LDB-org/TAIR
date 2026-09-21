"""Frozen paired evaluation of native multi-tool Pi and current generic TAIR plan."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

from expanded_reuse_cases import cases
from compare_pijit_presets import attempt

ROOT=Path(__file__).resolve().parents[1]


def main(out, continuation=False, task_ids=None, fresh=False):
    out=out.resolve();out.mkdir(exist_ok=False)
    jobs=cases()
    if continuation:
        from continuation_cases import cases as continuation_cases
        jobs.extend(continuation_cases())
    if fresh:
        from robustness_cases import cases as fresh_cases
        jobs.extend(fresh_cases())
    if task_ids:
        unknown=set(task_ids)-{j['id'] for j in jobs}
        if unknown:raise ValueError(f'Unknown tasks: {unknown}')
        jobs=[j for j in jobs if j['id'] in task_ids]
    rng=random.Random(731)
    schedule=[]
    for job in jobs:
        arms=['native','tair'];rng.shuffle(arms)
        schedule.extend((job['id'],arm) for arm in arms)
    sources={}
    for directory in ['deploy','integrations/pijit','benchmarks']:
        for p in (ROOT/directory).glob('*'):
            if p.suffix not in ('.py','.ts','.mjs'):continue
            relative=p.relative_to(ROOT);target=out/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target);sources[str(relative)]=hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(cases=jobs,schedule=schedule,source_sha256=sources,task_timeout=150,
                  method='New authored cases frozen before inference; sequential shuffled arm order per case, related-task order preserved. Same backend/workspace fixtures, separate state. TAIR seeded from a SQLite snapshot, never cleared between tasks; templates off. Native multi-tool enabled, all seven tools, max_tokens 17408 both arms. TAIR additionally enforces 2048 per child. Shared tunnel setup excluded. Agent time includes launch, all inference, recovery, tool execution and final reply; independent oracle separate. No harness retries or prompt/runtime changes after freeze. This is not an external held-out benchmark.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (out/'manifest.sha256').write_text(hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()+'\n')
    state_root=Path.home()/'测试'/('state-'+out.name);state_root.mkdir(exist_ok=False)
    rows=[];tunnel=None;tunnel_log=(out/'ssh-stderr.log').open('w')
    try:
        with tempfile.TemporaryDirectory(prefix='tair-expanded-project-') as temp:
            project=Path(temp)/'workspace';project.mkdir()
            source_book=Path.home()/'.pijit/workspaces'/hashlib.sha256(str((Path.home()/'测试').resolve()).encode()).hexdigest()[:20]/'tool-plan-codebook.sqlite3'
            dest_book=state_root/'tair/workspaces'/hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:20]/'tool-plan-codebook.sqlite3';dest_book.parent.mkdir(parents=True)
            with sqlite3.connect(source_book.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(dest_book) as dst:
                src.backup(dst)
                before=dst.execute('SELECT id,source_sha256,reuse_count FROM entries ORDER BY seq').fetchall()
            (out/'seed-book.json').write_text(json.dumps(before,indent=2))
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            tunnel=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'],stdout=subprocess.DEVNULL,stderr=tunnel_log)
            url=f'http://127.0.0.1:{port}'
            for _ in range(40):
                if tunnel.poll() is not None:raise RuntimeError(f'SSH tunnel exited with {tunnel.returncode}; see ssh-stderr.log')
                try:
                    if urllib.request.urlopen(url+'/health',timeout=2).status==200:break
                except Exception:time.sleep(.5)
            else:raise RuntimeError('Service unreachable')
            for key in list(os.environ):
                if key.startswith(('PIJIT_','TAIR_')):del os.environ[key]
            os.environ['PIJIT_URL']=url
            for task_id,arm in schedule:
                if tunnel.poll() is not None:
                    raise RuntimeError(f'SSH tunnel exited with {tunnel.returncode}; evaluation stopped')
                job=next(j for j in jobs if j['id']==task_id)
                shutil.rmtree(project);project.mkdir()
                for filename,content in job['files'].items():(project/filename).write_text(content)
                folder=out/(task_id+'-'+arm);folder.mkdir()
                overrides=dict(PIJIT_PYTHON=sys.executable,PIJIT_PLAN_ONLY='1' if arm=='tair' else '0',
                               PIJIT_TOOL_PLAN='1' if arm=='tair' else '0',PIJIT_PLAN_TEMPLATES='0',
                               PIJIT_NATIVE_PLANNER='1',TAIR_NATIVE_PARALLEL_TOOLS='1',TAIR_NATIVE_PREFIX_CACHE='1',
                               TAIR_NATIVE_MAX_TOKENS='17408',TAIR_NATIVE_TOOLS='read,edit,write,bash,grep,find,ls')
                try:
                    row=attempt(project,state_root/arm,folder,'native' if arm=='native' else 'c4',0,150,scenario=job,env_overrides=overrides)
                    row.update(arm=arm,task=task_id,group=job['group'],phase=job['phase'])
                    events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines() if l.startswith('{')]
                    completed=[r for r in row['metrics'] if r.get('action')=='tool_plan_complete']
                    row.update(reuse_executed=any(r.get('cache_hit') and r.get('status')=='ok' for r in completed),
                               tool_errors=sum(e.get('type')=='tool_execution_end' and bool(e.get('isError')) for e in events))
                    acc=[r['accounting'] for r in row['metrics']]
                    row.update({k:sum(a[k] for a in acc) for k in ['known_input_tokens','known_generated_argument_tokens','known_classification_control_records','inference_requests','unknown_usage_requests']})
                except Exception as exc:
                    import traceback
                    row=dict(task=task_id,arm=arm,passed=False,harness_error=traceback.format_exc(),usage_complete=False)
                shutil.copytree(project,folder/'project-after',ignore=shutil.ignore_patterns('__pycache__'))
                rows.append(row);(out/'report.json').write_text(json.dumps(rows,indent=2))
                print(json.dumps({k:v for k,v in row.items() if k in ['task','arm','passed','seconds','usage_complete','reuse_executed','tool_errors','known_generated_argument_tokens','inference_requests','harness_error']}),flush=True)
            with sqlite3.connect(dest_book) as db:
                (out/'final-book.json').write_text(json.dumps(db.execute('SELECT id,source_sha256,reuse_count FROM entries ORDER BY seq').fetchall(),indent=2))
            for relative,digest in sources.items():assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
    finally:
        if tunnel:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
        tunnel_log.close()
        for log in (state_root/'tair').glob('workspaces/*/plan-events.jsonl'):
            shutil.copyfile(log,out/'plan-events.jsonl')
        files=sorted(p for p in out.rglob('*') if p.is_file())
        (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--continuation',action='store_true')
    p.add_argument('--tasks',nargs='+')
    p.add_argument('--fresh',action='store_true')
    args=p.parse_args();main(args.out,args.continuation,args.tasks,args.fresh)
