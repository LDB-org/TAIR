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


def configuration(arm, revision, safe_codebook=False, planner_efficiency=False):
    flags = {k: '0' for k in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_PRESET_EDITS',
        'PIJIT_SERIAL_PREPARATION', 'PIJIT_CONTINUATION_CACHE', 'PIJIT_DIRECTORY_GUARD',
        'PIJIT_BATCH_TOOLS', 'PIJIT_PLAN_CONTEXT', 'PIJIT_LOCAL_ROUTING', 'PIJIT_BATCH_LOCAL_ROUTING')}
    hybrid = arm.startswith('hybrid')
    flags.update(PIJIT_DISABLE_CODEBOOK='1' if arm.endswith('_no_book') else '0',
                 PIJIT_SAFE_CODEBOOK='1' if safe_codebook and hybrid else '0',
                 PIJIT_COMPLETION_CHECKS='0',
                 PIJIT_PLANNER_EFFICIENCY='1' if planner_efficiency and hybrid and arm != 'hybrid_unoptimized' else '0',
                 PIJIT_NATIVE_PLANNER='1' if hybrid else '0',
                 PIJIT_BOUND_REUSE='1' if hybrid else '0',
                 PIJIT_NATIVE_PREFIX_CACHE='1' if hybrid else '0',
                 TAIR_NATIVE_PREFIX_CACHE='1' if arm.startswith('native') else '0',
                 PIJIT_TOKENIZER_REVISION=revision,
                 TAIR_NATIVE_PARALLEL_TOOLS='1' if arm == 'native_multi' else '0')
    if arm.startswith('tair') or hybrid:
        flags.update(PIJIT_BATCH_TOOLS='1', PIJIT_PLAN_CONTEXT='0' if hybrid else '1',
                     PIJIT_LOCAL_ROUTING='1', PIJIT_BATCH_LOCAL_ROUTING='1', PIJIT_DIRECTORY_GUARD='1')
    return flags


def main(args):
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    os.environ['PIJIT_URL'] = args.url
    scenarios = SCENARIOS
    if args.repository:
        if args.repository_suite == 'rich':
            from rich_repository_scenarios import scenarios_for
        else:
            from repository_scenarios import scenarios_for
        scenarios = scenarios_for(args.repository)
        if args.repository_expanded:
            from repository_transfer_scenarios import extra_scenarios
            scenarios.update(extra_scenarios(next(iter(scenarios.values()))['files']))
    if args.cases:
        scenarios = {name: scenarios[name] for name in args.cases}
    if args.warm_cases and not set(args.warm_cases) <= scenarios.keys():
        raise ValueError('Warm cases must belong to the selected suite')
    rounds_by_case = {name: args.rounds if args.warm_cases is None or name in args.warm_cases else 1
                      for name in scenarios}
    if args.rounds < 1 or args.repeats < 1 or args.timeout <= 0:
        raise ValueError('Rounds, repeats and timeout must be positive')
    for name, scenario in scenarios.items():
        if scenario.get('variants') and rounds_by_case[name] > len(scenario['variants']):
            raise ValueError('Too many rounds for task variants: ' + name)
    sources = [p for d in ['deploy', 'integrations/pijit', 'benchmarks'] for p in (ROOT/d).glob('*')
               if p.suffix in ('.py', '.ts', '.mjs', '.txt')]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for p in sources:
        dest = out / 'sources' / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
    manifest = {'arms': args.arms, 'cases': list(scenarios), 'rounds': args.rounds, 'repeats': args.repeats,
        'rounds_by_case': rounds_by_case,
        'source_sha256': hashes, 'configurations': {a: configuration(a,args.tokenizer_revision,args.safe_codebook,args.planner_efficiency) for a in args.arms},
        'planner_efficiency': args.planner_efficiency, 'safe_codebook': args.safe_codebook, 'repository_expanded': args.repository_expanded,
        'repository_suite': args.repository_suite,
        'completion_policy': '', 'seed': 923, 'repository': str(args.repository) if args.repository else None,
        'method': 'No extra completion policy or verification gate. Native single/multi differ only in parallel_tool_calls, and both permit workspace-scoped prefix caching. Hybrid retains native tool-call history and enables local bound codebook reuse; hybrid no_book/on differ only in disable-codebook. TAIR legacy keeps its classified batch planner and per-request cache salt. Sequential interleaving, no benchmark retries; all failures retained. Shared absolute task workspace across arms, independent per-arm state/cache namespaces, restored source for warm rounds, external oracle. Shared server and finite development tasks; no generic production claim.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (out/'scenarios.json').write_text(json.dumps(scenarios,indent=2))
    rng = random.Random(923); rows=[]
    with tempfile.TemporaryDirectory(prefix='tair-three-goals-') as temp:
        for repeat in range(args.repeats):
            for name, base_scenario in scenarios.items():
                for round_ in range(1,rounds_by_case[name]+1):
                    variants = base_scenario.get('variants')
                    scenario = {**base_scenario, **variants[round_ - 1]} if variants else base_scenario
                    order=list(args.arms);rng.shuffle(order)
                    for arm in order:
                        root=Path(temp)/f'{repeat}-{name}'
                        project,state=root/'project',root/'states'/arm
                        if project.exists():shutil.rmtree(project)
                        project.mkdir(parents=True)
                        for path,content in scenario['files'].items():
                            target=project/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
                        folder=out/f'{repeat}-{name}-{arm}-{round_}';folder.mkdir()
                        native=arm.startswith('native')
                        row=b.attempt(project,state,folder,'native' if native else 'c4',0,args.timeout,
                            scenario=scenario,env_overrides=configuration(arm,args.tokenizer_revision,args.safe_codebook,args.planner_efficiency),
                            append_system_prompt=None)
                        row.update(arm=arm,case=name,repeat=repeat,round=round_,order=order,
                                   task_variant='cold' if round_==1 else 'new_binding' if variants and round_>2 else 'exact_repeat')
                        try:row['test_integrity']=test_integrity(project,name,scenario)
                        except (OSError,SyntaxError):row['test_integrity']=False
                        protected=[path for path in scenario.get('protected',[]) if not (project/path).is_file() or (project/path).read_text()!=scenario['files'][path]]
                        if scenario.get('protected'):
                            protected += sorted(str(p.relative_to(project)) for p in project.rglob('*')
                                if p.is_file() and '__pycache__' not in p.parts and str(p.relative_to(project)) not in scenario['files'])
                        row['protected_changes']=protected
                        row['passed'] &= row['test_integrity'] and not protected
                        shutil.copytree(project,folder/'project-after',ignore=shutil.ignore_patterns('__pycache__'))
                        for book in state.glob('workspaces/*/codebook.json'):shutil.copyfile(book,folder/'codebook.json')
                        events=[]
                        for line in (folder/'events.jsonl').read_text().splitlines():
                            try:events.append(json.loads(line))
                            except ValueError:pass
                        row['multi_tool_responses']=sum(sum(c.get('type')=='toolCall' for c in e.get('message',{}).get('content',[]) if isinstance(c,dict))>1 for e in events if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant')
                        row['tool_errors']=sum(e.get('type')=='tool_execution_end' and e.get('isError',False) for e in events)
                        (folder/'final-result.json').write_text(json.dumps(row,indent=2))
                        rows.append(row)
                        with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                        print(json.dumps({k:row[k] for k in ['arm','case','round','passed','validated_seconds','multi_tool_responses']}),flush=True)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in hashes.items())
    summary = b.summarize(rows)
    summary['limitations'] = manifest['method']
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    return int(not all(r['passed'] and r['usage_complete'] for r in rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--url',required=True)
    parser.add_argument('--tokenizer-revision',required=True)
    parser.add_argument('--arms',nargs='+',choices=['native_single','native_multi','tair_no_book','tair','hybrid_no_book','hybrid','hybrid_unoptimized'],default=['native_single','native_multi','tair','hybrid'])
    parser.add_argument('--cases',nargs='+');parser.add_argument('--rounds',type=int,default=2)
    parser.add_argument('--warm-cases',nargs='+',help='Only these cases receive rounds after the cold round')
    parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--timeout',type=float,default=120)
    parser.add_argument('--repository',type=Path)
    parser.add_argument('--repository-suite',choices=['cpython','rich'],default='cpython')
    parser.add_argument('--planner-efficiency',action='store_true')
    parser.add_argument('--safe-codebook',action='store_true',help='Use conservative persisted reuse in both hybrid arms')
    parser.add_argument('--repository-expanded',action='store_true',help='Add held-out CPython script tasks')
    raise SystemExit(main(parser.parse_args()))
