"""Correctness, native multi-tool reference and routed codebook comparisons."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import tempfile

from benchmark_codebook_agent import b, test_integrity
from expanded_agent_scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
POLICY = (ROOT / 'integrations/pijit/requirements.txt').read_text()


def configuration(arm, revision):
    flags = {k: '0' for k in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_PRESET_EDITS',
        'PIJIT_SERIAL_PREPARATION', 'PIJIT_CONTINUATION_CACHE', 'PIJIT_DIRECTORY_GUARD',
        'PIJIT_BATCH_TOOLS', 'PIJIT_PLAN_CONTEXT', 'PIJIT_LOCAL_ROUTING', 'PIJIT_BATCH_LOCAL_ROUTING')}
    flags.update(PIJIT_DISABLE_CODEBOOK='1' if arm == 'tair_no_book' else '0',
                 PIJIT_COMPLETION_CHECKS='1', PIJIT_VERIFY_COMPLETION='1' if arm.startswith('tair') else '0',
                 PIJIT_TOKENIZER_REVISION=revision,
                 TAIR_NATIVE_PARALLEL_TOOLS='1' if arm == 'native_multi' else '0')
    if arm.startswith('tair'):
        flags.update(PIJIT_BATCH_TOOLS='1', PIJIT_PLAN_CONTEXT='1',
                     PIJIT_LOCAL_ROUTING='1', PIJIT_BATCH_LOCAL_ROUTING='1', PIJIT_DIRECTORY_GUARD='1')
    return flags


def main(args):
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    os.environ['PIJIT_URL'] = args.url
    scenarios = SCENARIOS
    if args.repository:
        from repository_scenarios import scenarios_for
        scenarios = scenarios_for(args.repository)
    if args.cases:
        scenarios = {name: scenarios[name] for name in args.cases}
    sources = [p for d in ['deploy', 'integrations/pijit', 'benchmarks'] for p in (ROOT/d).glob('*')
               if p.suffix in ('.py', '.ts', '.mjs', '.txt')]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for p in sources:
        dest = out / 'sources' / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
    manifest = {'arms': args.arms, 'cases': list(scenarios), 'rounds': args.rounds, 'repeats': args.repeats,
        'source_sha256': hashes, 'configurations': {a: configuration(a,args.tokenizer_revision) for a in args.arms},
        'completion_policy': POLICY, 'seed': 923, 'repository': str(args.repository) if args.repository else None,
        'method': 'Same completion policy for native and TAIR. Native single/multi differ only in parallel_tool_calls. TAIR no_book/on differ only in disable-codebook; both use local routing within batch mode. Sequential interleaving, no retries, all failures retained. Fresh per-arm state; restored identical source for warm rounds; final oracle external to Agent. Shared server, finite development suite; no claim of generic production performance.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (out/'scenarios.json').write_text(json.dumps(scenarios,indent=2))
    rng = random.Random(923); rows=[]
    with tempfile.TemporaryDirectory(prefix='tair-three-goals-') as temp:
        for repeat in range(args.repeats):
            for name, base_scenario in scenarios.items():
                for round_ in range(1,args.rounds+1):
                    variants = base_scenario.get('variants')
                    scenario = {**base_scenario, **variants[round_ - 1]} if variants else base_scenario
                    order=list(args.arms);rng.shuffle(order)
                    for arm in order:
                        root=Path(temp)/f'{repeat}-{name}-{arm}'
                        project,state=root/'project',root/'state'
                        if project.exists():shutil.rmtree(project)
                        project.mkdir(parents=True)
                        for path,content in scenario['files'].items():
                            target=project/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
                        folder=out/f'{repeat}-{name}-{arm}-{round_}';folder.mkdir()
                        native=arm.startswith('native')
                        row=b.attempt(project,state,folder,'native' if native else 'c4',0,args.timeout,
                            scenario=scenario,env_overrides=configuration(arm,args.tokenizer_revision),
                            append_system_prompt=POLICY if native else None)
                        row.update(arm=arm,case=name,repeat=repeat,round=round_,order=order,
                                   task_variant='cold' if round_==1 else 'exact_repeat' if round_==2 else 'new_binding')
                        try:row['test_integrity']=test_integrity(project,name,scenario)
                        except (OSError,SyntaxError):row['test_integrity']=False
                        protected=[path for path in scenario.get('protected',[]) if not (project/path).is_file() or (project/path).read_text()!=scenario['files'][path]]
                        row['protected_changes']=protected
                        row['passed'] &= row['test_integrity'] and not protected
                        (folder/'final-result.json').write_text(json.dumps(row,indent=2))
                        shutil.copytree(project,folder/'project-after',ignore=shutil.ignore_patterns('__pycache__'))
                        for book in state.glob('workspaces/*/codebook.json'):shutil.copyfile(book,folder/'codebook.json')
                        events=[]
                        for line in (folder/'events.jsonl').read_text().splitlines():
                            try:events.append(json.loads(line))
                            except ValueError:pass
                        row['multi_tool_responses']=sum(sum(c.get('type')=='toolCall' for c in e.get('message',{}).get('content',[]) if isinstance(c,dict))>1 for e in events if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant')
                        row['tool_errors']=sum(e.get('type')=='tool_execution_end' and e.get('isError',False) for e in events)
                        rows.append(row)
                        with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                        print(json.dumps({k:row[k] for k in ['arm','case','round','passed','validated_seconds','multi_tool_responses']}),flush=True)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in hashes.items())
    (out/'summary.json').write_text(json.dumps(b.summarize(rows),indent=2))
    return int(not all(r['passed'] and r['usage_complete'] for r in rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--url',required=True)
    parser.add_argument('--tokenizer-revision',required=True)
    parser.add_argument('--arms',nargs='+',choices=['native_single','native_multi','tair_no_book','tair'],default=['native_single','native_multi','tair'])
    parser.add_argument('--cases',nargs='+');parser.add_argument('--rounds',type=int,default=2)
    parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--timeout',type=float,default=120)
    parser.add_argument('--repository',type=Path)
    raise SystemExit(main(parser.parse_args()))
