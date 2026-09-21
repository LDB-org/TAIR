"""Frozen paired evaluation of native multi-tool Pi and current generic TAIR plan."""
import argparse
import copy
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


def wait_backend_idle(url, timeout=210):
    started=time.perf_counter()
    while time.perf_counter()-started < timeout:
        metrics=urllib.request.urlopen(url+'/metrics',timeout=10).read().decode()
        active=[float(line.rsplit(' ',1)[-1]) for line in metrics.splitlines()
                if line.startswith(('vllm:num_requests_running{','vllm:num_requests_waiting{'))]
        if active and all(value==0 for value in active):
            return dict(seconds=time.perf_counter()-started, idle=True)
        time.sleep(1)
    raise RuntimeError('Backend still active after a timed-out task; stopping before the next arm')



def repeat_cases(jobs, count):
    if count < 1:
        raise ValueError('Repeat count must be positive')
    result = []
    for job in jobs:
        for index in range(count if job['phase']=='repeat' else 1):
            item = copy.deepcopy(job)
            if index:
                item['id'] += '_'+str(index+1)
            result.append(item)
    return result


def main(out, continuation=False, task_ids=None, fresh=False, local_tokenizer=None, verify_tokenizer=False, prefix_cache=False, compact_catalog=False, reuse_routing=False, ssh_compression=False, ablation=False, empty_book=False, success_reply_ablation=False, recovery_latest=False, recovery_ablation=False, capabilities_ablation=False, execution_ablation=False, reuse_review_ablation=False, write_references_ablation=False, recovery_admission_ablation=False, warm_reuse_ablation=False, repeat_count=1, argv_ablation=False):
    if argv_ablation and any((warm_reuse_ablation, recovery_admission_ablation, write_references_ablation, reuse_review_ablation, execution_ablation, success_reply_ablation, recovery_ablation, capabilities_ablation, recovery_latest, reuse_routing, compact_catalog)):
        raise ValueError('Bash argv ablation must isolate only command representation')
    if warm_reuse_ablation and (recovery_admission_ablation or write_references_ablation or reuse_review_ablation or execution_ablation or success_reply_ablation or recovery_ablation or capabilities_ablation or recovery_latest or reuse_routing or compact_catalog):
        raise ValueError("Warm reuse ablation must isolate only content reuse")
    if recovery_admission_ablation and (write_references_ablation or reuse_review_ablation or execution_ablation or success_reply_ablation or recovery_ablation or capabilities_ablation or recovery_latest or reuse_routing or compact_catalog):
        raise ValueError("Recovery admission ablation must isolate only recovered content admission")
    if write_references_ablation and (reuse_review_ablation or execution_ablation or success_reply_ablation or recovery_ablation or capabilities_ablation or recovery_latest or reuse_routing or compact_catalog):
        raise ValueError("Write reference ablation must isolate the write payload format")
    if reuse_review_ablation and (execution_ablation or success_reply_ablation or recovery_ablation or capabilities_ablation or recovery_latest):
        raise ValueError('Reuse review ablation must isolate only the reuse decision format')
    if execution_ablation and (success_reply_ablation or recovery_ablation or capabilities_ablation or recovery_latest):
        raise ValueError('Execution guidance ablation must isolate only planning guidance')
    if capabilities_ablation and (success_reply_ablation or recovery_ablation or recovery_latest):
        raise ValueError('Capabilities ablation must isolate only metadata caching')
    if recovery_ablation and (success_reply_ablation or recovery_latest):
        raise ValueError('Recovery ablation requires separate old/new routing and no reply ablation')
    if success_reply_ablation or recovery_ablation or capabilities_ablation or execution_ablation or reuse_review_ablation or write_references_ablation or recovery_admission_ablation or warm_reuse_ablation or argv_ablation:
        ablation = True
    cli = shutil.which('pi')
    if not cli:
        raise RuntimeError('Pi 0.85.1 must be in PATH before benchmarking')
    package = Path(cli).resolve().parents[2] / 'package.json'
    if not package.is_file() or json.loads(package.read_text()).get('version') != '0.85.1':
        raise RuntimeError('Benchmark requires the pinned Pi 0.85.1 installation in PATH')
    out=out.resolve();out.mkdir(exist_ok=False)
    jobs=cases()
    if recovery_admission_ablation:
        from recovery_admission_cases import cases as recovery_cases
        jobs.extend(recovery_cases())
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
    jobs=repeat_cases(jobs,repeat_count)
    rng=random.Random(731)
    schedule=[]
    configured_arms=['native','tair_no_reuse','tair'] if ablation else ['native','tair']
    if success_reply_ablation:
        configured_arms=['native','tair_no_reuse','tair_reply']
    if recovery_ablation:
        configured_arms=['native','tair_no_reuse','tair_recovery']
    if capabilities_ablation:
        configured_arms=['native','tair_no_reuse','tair_capcache']
    if execution_ablation:
        configured_arms=['native','tair','tair_guided']
    if reuse_review_ablation:
        configured_arms=['native','tair','tair_review']
    if write_references_ablation:
        configured_arms=['native','tair','tair_refs']
    if recovery_admission_ablation:
        configured_arms=['native','tair_refs','tair_recovered']
    if warm_reuse_ablation:
        configured_arms=['native','tair_no_reuse','tair_refs']
    if argv_ablation:
        configured_arms=['native','tair_no_reuse','tair_argv']
    plan_arms=[arm for arm in configured_arms if arm!='native']
    for job in jobs:
        arms=configured_arms.copy();rng.shuffle(arms)
        schedule.extend((job['id'],arm) for arm in arms)
    sources={}
    for directory in ['deploy','integrations/pijit','benchmarks']:
        for p in (ROOT/directory).glob('*'):
            if p.suffix not in ('.py','.ts','.mjs'):continue
            relative=p.relative_to(ROOT);target=out/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target);sources[str(relative)]=hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(cases=jobs,schedule=schedule,source_sha256=sources,task_timeout=150,
                  method='New authored cases frozen before inference; sequential shuffled arm order per case, related-task order preserved. Same backend/workspace fixtures, separate state. TAIR seeded from a SQLite snapshot, never cleared between tasks; templates off. Native multi-tool enabled, all seven tools, max_tokens 17408 both arms. TAIR additionally enforces 2048 per child. Shared tunnel setup excluded. Agent time includes launch, all inference, recovery, tool execution and final reply; independent oracle separate. No harness retries or prompt/runtime changes after freeze. This is not an external held-out benchmark.')
    tokenizer_revision = None
    if local_tokenizer:
        snapshot = (local_tokenizer / 'manifest.json').read_bytes()
        tokenizer_revision = hashlib.sha256(snapshot).hexdigest()
        manifest.update(local_tokenizer_manifest=json.loads(snapshot), tokenizer_revision=tokenizer_revision,
                        verify_local_tokenizer=verify_tokenizer)
    manifest['arms'] = configured_arms
    manifest['initial_codebook'] = 'empty isolated state' if empty_book else 'read-only user snapshot'
    manifest['reuse_ablation'] = ablation and not success_reply_ablation and not recovery_ablation and not capabilities_ablation and not execution_ablation and not reuse_review_ablation and not write_references_ablation and not recovery_admission_ablation and not warm_reuse_ablation and not argv_ablation
    manifest['bash_argv_ablation'] = argv_ablation
    manifest['warm_reuse_ablation'] = warm_reuse_ablation
    manifest['repeat_count'] = repeat_count
    manifest['recovery_admission_ablation'] = recovery_admission_ablation
    manifest['write_references_ablation'] = write_references_ablation
    manifest['reuse_review_ablation'] = reuse_review_ablation
    manifest['execution_guidance_ablation'] = execution_ablation
    manifest['capabilities_ablation'] = capabilities_ablation
    manifest['recovery_ablation'] = recovery_ablation
    manifest['success_reply_ablation'] = success_reply_ablation
    manifest['recovery_latest'] = recovery_latest
    manifest['timeout_barrier'] = 'After a task timeout, require running=waiting=0 before next arm; barrier outside task timing, recorded separately.'
    manifest['method'] = manifest['method'].replace('TAIR seeded from a SQLite snapshot', 'TAIR starts with empty isolated books' if empty_book else 'TAIR seeded from a SQLite snapshot')
    manifest['pi_version'] = '0.85.1'
    manifest['pi_cli'] = str(Path(cli).resolve())
    manifest['tair_session_prefix_cache'] = prefix_cache
    manifest['tair_compact_catalog'] = compact_catalog
    manifest['tair_reuse_routing'] = reuse_routing
    manifest['ssh_compression_both_arms'] = ssh_compression
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (out/'manifest.sha256').write_text(hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()+'\n')
    state_root=Path.home()/'测试'/('state-'+out.name);state_root.mkdir(exist_ok=False)
    rows=[];tunnel=None;tunnel_log=(out/'ssh-stderr.log').open('w')
    try:
        with tempfile.TemporaryDirectory(prefix='tair-expanded-project-') as temp:
            project=Path(temp)/'workspace';project.mkdir()
            source_book=Path.home()/'.pijit/workspaces'/hashlib.sha256(str((Path.home()/'测试').resolve()).encode()).hexdigest()[:20]/'tool-plan-codebook.sqlite3'
            dest_books={}
            for plan_arm in plan_arms:
                dest_book=state_root/plan_arm/'workspaces'/hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:20]/'tool-plan-codebook.sqlite3'
                dest_book.parent.mkdir(parents=True)
                dest_books[plan_arm]=dest_book
                before=[]
                if not empty_book:
                    with sqlite3.connect(source_book.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(dest_book) as dst:
                        src.backup(dst)
                        before=dst.execute('SELECT id,source_sha256,reuse_count FROM entries ORDER BY seq').fetchall()
                seed_name='seed-book-'+plan_arm+'.json' if ablation else 'seed-book.json'
                (out/seed_name).write_text(json.dumps(before,indent=2))
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            tunnel=subprocess.Popen(['ssh','-N','-o','Compression='+('yes' if ssh_compression else 'no'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-L',f'127.0.0.1:{port}:127.0.0.1:8000','rs-yuesheng-gpu-public'],stdout=subprocess.DEVNULL,stderr=tunnel_log)
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
            (out/'initial-idle.json').write_text(json.dumps(wait_backend_idle(url),indent=2))
            for task_id,arm in schedule:
                if tunnel.poll() is not None:
                    raise RuntimeError(f'SSH tunnel exited with {tunnel.returncode}; evaluation stopped')
                job=next(j for j in jobs if j['id']==task_id)
                shutil.rmtree(project);project.mkdir()
                for filename,content in job['files'].items():(project/filename).write_text(content)
                folder=out/(task_id+'-'+arm);folder.mkdir()
                overrides=dict(PIJIT_PYTHON=sys.executable,PIJIT_PLAN_ONLY='0' if arm=='native' else '1',
                               PIJIT_TOOL_PLAN='0' if arm=='native' else '1',PIJIT_PLAN_TEMPLATES='0',
                               PIJIT_NATIVE_PLANNER='1',TAIR_NATIVE_PARALLEL_TOOLS='1',TAIR_NATIVE_PREFIX_CACHE='1',
                               TAIR_NATIVE_MAX_TOKENS='17408',TAIR_NATIVE_TOOLS='read,edit,write,bash,grep,find,ls')
                if arm != 'native' and local_tokenizer:
                    overrides.update(PIJIT_LOCAL_TOKENIZER=str(local_tokenizer.resolve()),
                                     PIJIT_TOKENIZER_REVISION=tokenizer_revision,
                                     PIJIT_LOCAL_TOKENIZER_VERIFY='1' if verify_tokenizer else '0')
                if arm != 'native' and reuse_routing:
                    overrides['PIJIT_REUSE_ROUTING']='1'
                if arm != 'native' and compact_catalog:
                    overrides['PIJIT_COMPACT_CATALOG']='1'
                if arm != 'native' and prefix_cache:
                    overrides['PIJIT_PREFIX_CACHE']='1'
                overrides['PIJIT_PLAN_DISABLE_REUSE']='1' if arm in ('tair_no_reuse','tair_reply','tair_recovery','tair_capcache','tair_argv') else '0'
                overrides['PIJIT_PLAN_SUCCESS_REPLY']='1' if arm=='tair_reply' else '0'
                references_for_arm = arm in ('tair_refs','tair_recovered') or warm_reuse_ablation and arm!='native'
                admission_for_arm = arm=='tair_recovered' or warm_reuse_ablation and arm!='native'
                overrides['PIJIT_BASH_ARGV']='1' if arm=='tair_argv' else '0'
                overrides['PIJIT_WRITE_REFERENCES']='1' if references_for_arm else '0'
                overrides['PIJIT_RECOVERY_ADMISSION']='1' if admission_for_arm else '0'
                overrides['PIJIT_REUSE_REVIEW']='1' if arm=='tair_review' else '0'
                overrides['PIJIT_PLAN_EXECUTION_GUIDANCE']='1' if arm=='tair_guided' else '0'
                overrides['PIJIT_CAPABILITIES_CACHE']='1' if arm=='tair_capcache' else '0'
                latest_for_arm = arm=='tair_recovery' or arm!='native' and recovery_latest
                overrides['PIJIT_RECOVERY_LATEST']='1' if latest_for_arm else '0'
                try:
                    row=attempt(project,state_root/arm,folder,'native' if arm=='native' else 'c4',0,150,scenario=job,env_overrides=overrides)
                    row.update(arm=arm,task=task_id,group=job['group'],phase=job['phase'])
                    events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines() if l.startswith('{')]
                    completed=[r for r in row['metrics'] if r.get('action')=='tool_plan_complete']
                    row.update(reuse_executed=any(r.get('cache_hit') and r.get('status')=='ok' for r in completed),
                               tool_errors=sum(e.get('type')=='tool_execution_end' and bool(e.get('isError')) for e in events))
                    if arm!='native':
                        chats=[m for m in row['metrics'] if m.get('generic_plan') and m.get('action')=='chat']
                        assert chats and all(m.get('plan_reuse_enabled')==(arm not in ('tair_no_reuse','tair_reply','tair_recovery','tair_capcache','tair_argv')) for m in chats), 'Runtime reuse configuration mismatch'
                        assert all(m.get('plan_success_reply_enabled')==(arm=='tair_reply') for m in chats), 'Runtime reply configuration mismatch'
                        assert all(m.get('recovery_scope')==('latest_result' if latest_for_arm else 'whole_user_turn') for m in chats), 'Runtime recovery configuration mismatch'
                        assert all(m.get('recovery_admission_enabled')==admission_for_arm for m in chats), 'Runtime recovery admission mismatch'
                        assert all(m.get('bash_argv_enabled')==(arm=='tair_argv') for m in chats), 'Runtime bash argv mismatch'
                        assert all(m.get('write_references_enabled')==references_for_arm for m in chats), 'Runtime write reference mismatch'
                        assert all(m.get('reuse_review_enabled')==(arm=='tair_review') for m in chats), 'Runtime reuse review mismatch'
                        assert all(m.get('execution_guidance_enabled')==(arm=='tair_guided') for m in chats), 'Runtime execution guidance mismatch'
                        assert all(m.get('capabilities_cache_enabled')==(arm=='tair_capcache') for m in chats), 'Runtime capabilities cache mismatch'
                    acc=[r['accounting'] for r in row['metrics']]
                    row.update({k:sum(a[k] for a in acc) for k in ['known_input_tokens','known_generated_argument_tokens','known_classification_control_records','inference_requests','unknown_usage_requests']})
                except Exception as exc:
                    import traceback
                    row=dict(task=task_id,arm=arm,passed=False,harness_error=traceback.format_exc(),usage_complete=False)
                shutil.copytree(project,folder/'project-after',ignore=shutil.ignore_patterns('__pycache__'))
                rows.append(row);(out/'report.json').write_text(json.dumps(rows,indent=2))
                if row.get('harness_error'):
                    raise RuntimeError('Harness failed; stopping with original evidence retained')
                if row.get('timed_out'):
                    (folder/'post-timeout-idle.json').write_text(json.dumps(wait_backend_idle(url),indent=2))
                print(json.dumps({k:v for k,v in row.items() if k in ['task','arm','passed','seconds','usage_complete','reuse_executed','tool_errors','known_generated_argument_tokens','inference_requests','harness_error']}),flush=True)
            for plan_arm,dest_book in dest_books.items():
                final=[]
                if dest_book.exists():
                    with sqlite3.connect(dest_book) as db:
                        final=db.execute('SELECT id,source_sha256,reuse_count FROM entries ORDER BY seq').fetchall()
                final_name='final-book-'+plan_arm+'.json' if ablation else 'final-book.json'
                (out/final_name).write_text(json.dumps(final,indent=2))
            for relative,digest in sources.items():assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
    finally:
        if tunnel:
            tunnel.terminate()
            try:tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
        tunnel_log.close()
        for plan_arm in plan_arms:
            for log in (state_root/plan_arm).glob('workspaces/*/plan-events.jsonl'):
                shutil.copyfile(log,out/('plan-events-'+plan_arm+'.jsonl' if ablation else 'plan-events.jsonl'))
        files=sorted(p for p in out.rglob('*') if p.is_file())
        (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))+'\n' for p in files))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--continuation',action='store_true')
    p.add_argument('--tasks',nargs='+')
    p.add_argument('--fresh',action='store_true')
    p.add_argument('--local-tokenizer',type=Path)
    p.add_argument('--verify-tokenizer',action='store_true')
    p.add_argument('--prefix-cache',action='store_true')
    p.add_argument('--compact-catalog',action='store_true')
    p.add_argument('--reuse-routing',action='store_true')
    p.add_argument('--ssh-compression',action='store_true')
    p.add_argument('--ablation',action='store_true')
    p.add_argument('--empty-book',action='store_true')
    p.add_argument('--success-reply-ablation',action='store_true')
    p.add_argument('--recovery-latest',action='store_true')
    p.add_argument('--recovery-ablation',action='store_true')
    p.add_argument('--capabilities-ablation',action='store_true')
    p.add_argument('--execution-ablation',action='store_true')
    p.add_argument('--reuse-review-ablation',action='store_true')
    p.add_argument('--write-references-ablation',action='store_true')
    p.add_argument('--recovery-admission-ablation',action='store_true')
    p.add_argument('--warm-reuse-ablation',action='store_true')
    p.add_argument('--argv-ablation',action='store_true')
    p.add_argument('--repeat-count',type=int,default=1)
    args=p.parse_args();main(args.out,args.continuation,args.tasks,args.fresh,args.local_tokenizer,args.verify_tokenizer,args.prefix_cache,args.compact_catalog,args.reuse_routing,args.ssh_compression,args.ablation,args.empty_book,args.success_reply_ablation,args.recovery_latest,args.recovery_ablation,args.capabilities_ablation,args.execution_ablation,args.reuse_review_ablation,args.write_references_ablation,args.recovery_admission_ablation,args.warm_reuse_ablation,args.repeat_count,args.argv_ablation)
