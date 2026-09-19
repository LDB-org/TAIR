"""Persistent generate/verify/admit/reuse through the real Pi compact_edit bridge.

Each attempt starts a fresh process; cold states are empty. Not a full Agent.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCE="import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument('--workers', type=int, default=4, help='workers')\n    p.add_argument('--timeout', type=int, default=3, help='timeout')\n    return p\n"
GUARD='def divide(a, b):\n    return a / b\n'


def cases():
    def cli(name,task,workers=4,timeout=3,help='timeout',alias=None,**kw):
        return dict(name=name,task=task,kind='cli',source=SOURCE,workers=workers,timeout=timeout,help=help,alias=alias,verify=True,**kw)
    def guard(name,value,verify=True):
        return dict(name=name,task=f'Return {value} from divide when b == 0.',kind='guard',source=GUARD,result=value,verify=verify)
    result=[cli('cold_default','Change --workers default to 6.',6),
        cli('repeat_default','Change --workers default to 6.',6),
        cli('new_parameter','Change --workers default to 8.',8),
        cli('updated_snapshot','Change --workers default to 10.',10,previous=True),
        cli('cold_help','Change --timeout help to "Wait duration".',help='Wait duration'),
        cli('new_help','Change --timeout help to "Deadline".',help='Deadline'),
        cli('cold_alias','Add alias -w to --workers.',alias='-w'),
        cli('new_alias','Add alias -x to --workers.',alias='-x'),
        cli('compound_cold','Change --workers default to 8 and --timeout default to 5.',8,5),
        cli('compound_repeat','Change --workers default to 8 and --timeout default to 5.',8,5),
        cli('negated_scope','Do not change --workers. Change --timeout default to 7.',4,7),
        guard('guard_cold','None'),guard('guard_repeat','None'),guard('changed_guard','0'),
        cli('stale_source','Change --workers default to 6.',6),
        guard('unverified_no_admission','None',False)]
    result[-2]['source']+='NEW_VERSION = True\n'
    return result


def expanded_cases():
    result = cases()
    warm = {'repeat_default', 'new_parameter', 'updated_snapshot', 'new_help',
            'new_alias', 'compound_repeat', 'guard_repeat'}
    for case in result:
        case['expect_reuse'] = case['name'] in warm
    def add(name, base, task=None, reuse=False, **changes):
        case = dict(result[base], name=name, expect_reuse=reuse)
        case.pop('previous', None)
        if task is not None:
            case['task'] = task
        case.update(changes)
        result.append(case)
    add('halve_workers', 0, 'Halve the default for --workers; leave --timeout unchanged.', workers=2)
    add('halve_repeat', 16, reuse=True)
    add('compound_different_values', 8, 'Change --workers default to 12 and --timeout default to 9.', workers=12, timeout=9)
    add('compound_different_repeat', 18, reuse=True)
    add('negation_reverse', 0, 'Do not change --timeout. Change --workers default to 11.', workers=11)
    add('negation_reverse_repeat', 20, reuse=True)
    add('unicode_help', 4, 'Change --timeout help to "等待秒数".', help='等待秒数', reuse=True)
    add('negative_default', 0, 'Change --workers default to -2.', workers=-2, reuse=True)
    add('zero_default', 0, 'Change --workers default to 0.', workers=0, reuse=True)
    add('comment_only_source', 0, source='# A formatting-only revision\n' + SOURCE, reuse=True)
    add('different_path', 0, project='other')
    add('different_path_repeat', 26, reuse=True)
    add('changed_verifier', 11, verify_suffix=' # verifier-v2')
    add('changed_verifier_repeat', 28)
    add('original_verifier_restored', 11, reuse=True)
    add('paraphrased_guard', 11, 'If b equals zero, return None in divide; otherwise retain the division.')
    add('paraphrased_guard_repeat', 31, reuse=True)
    add('unverified_repeat', 15)
    return result


def check_code(case):
    if case['kind']=='guard':
        return f"import sys;sys.path.insert(0,'.');import app;assert app.divide(9,3)==3;assert app.divide(1,0) is {case['result']}\n"
    return f'''import sys
sys.path.insert(0,'.')
import app
p=app.build_parser()
n=p.parse_args([])
assert n.workers=={case['workers']} and n.timeout=={case['timeout']}
n=p.parse_args(['--workers','23','--timeout','29'])
assert n.workers==23 and n.timeout==29
opt=next(a for a in p._actions if '--timeout' in a.option_strings)
assert opt.help=={case['help']!r}
'''+(f"assert p.parse_args([{case['alias']!r},'19']).workers==19\n" if case['alias'] else '')


def expected_ast(source,case):
    if case['kind']=='guard':
        return ast.dump(ast.parse(GUARD.replace('    return a / b',f"    if b == 0:\n        return {case['result']}\n    return a / b")))
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr!='add_argument':continue
        option=node.args[0].value
        for keyword in node.keywords:
            if keyword.arg=='default':keyword.value=ast.Constant(case['workers'] if option=='--workers' else case['timeout'])
            if keyword.arg=='help' and option=='--timeout':keyword.value=ast.Constant(case['help'])
        if option=='--workers' and case['alias']:node.args.append(ast.Constant(case['alias']))
        node.args.sort(key=lambda a:a.value)
    return ast.dump(tree)


def normalize(source):
    tree=ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='add_argument':
            node.args.sort(key=lambda a:a.value)
    return ast.dump(tree)


def main(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    snapshot=out/'sources';snapshot.mkdir()
    for path in [ROOT/'integrations/pijit/bridge.py',*sorted((ROOT/'deploy').glob('*.py')),Path(__file__)]:
        dst=snapshot/path.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst)
    allcases=expanded_cases() if args.suite=='expanded' else cases();arms=['generate','safe_book'];rng=random.Random(20260923)
    (out/'manifest.json').write_text(json.dumps(dict(cases=allcases,repeats=args.repeats,arms=arms,
        scope='Real compact_edit bridge, fresh process every task, persistent per-arm state. Single edit stage, not full Agent.',
        learning='Initially empty book, no preloaded answers. Cases ordered to test learning; arms interleaved randomly within each step. Current configured project check reruns on every application.',
        validation='Runtime behavioral check validates task behavior; independent AST oracle checks other code. Checks never sent to model.',
        timing='Process startup, preparation, model calls, writing, runtime verification and external AST/behavior verification included; fixture reset and validator file setup excluded.'),indent=2))
    workspace=out/'workspace';workspace.mkdir()
    rows=[]
    for repeat in range(args.repeats):
        previous={}
        for case in allcases:
            shuffled=arms[:];rng.shuffle(shuffled)
            for arm in shuffled:
                project=workspace/case.get('project','main');project.mkdir(exist_ok=True)
                state=out/'state'/f'{repeat}-{arm}';state.mkdir(parents=True,exist_ok=True)
                source=previous.get(arm,case['source']) if case.get('previous') else case['source']
                (project/'app.py').write_text(source)
                validator=out/'current-check.py';validator.write_text(check_code(case))
                env={k:v for k,v in os.environ.items() if not k.startswith('PIJIT_')}
                env.update(PIJIT_URL=args.url,PIJIT_MODEL='/model',PIJIT_STATE_DIR=str(state),PIJIT_SAFE_CODEBOOK='1',
                           PYTHONDONTWRITEBYTECODE='1')
                if arm=='generate':env['PIJIT_DISABLE_CODEBOOK']='1'
                if case['verify']:env['PIJIT_VERIFY_CMD']=shlex.join([sys.executable,'-B',str(validator)])+case.get('verify_suffix','')
                payload=dict(action='edit',cwd=str(project),path='app.py',task=case['task'])
                folder=out/'attempts'/str(len(rows));folder.mkdir(parents=True)
                (folder/'before.py').write_text(source);(folder/'payload.json').write_text(json.dumps(payload))
                (folder/'behavior-check.py').write_text(check_code(case))
                books=list(state.rglob('codebook.json'))
                if books:shutil.copyfile(books[0],folder/'book-before.json')
                row=dict(arm=arm,case=case['name'],repeat=repeat,passed=False)
                start=time.perf_counter()
                try:
                    run=subprocess.run([sys.executable,str(ROOT/'integrations/pijit/bridge.py')],input=json.dumps(payload),
                        text=True,capture_output=True,cwd=ROOT,env=env,timeout=180)
                    (folder/'stdout.txt').write_text(run.stdout);(folder/'stderr.txt').write_text(run.stderr)
                    response=json.loads(run.stdout);row['response']=response
                    assert response['status']=='ok',response.get('error')
                    updated=(project/'app.py').read_text()
                    assert normalize(updated)==expected_ast(source,case),'Unrelated AST change or incorrect operation'
                    checked=subprocess.run([sys.executable,'-B',str(validator)],cwd=project,capture_output=True,text=True,timeout=10)
                    assert checked.returncode==0,checked.stderr
                    row['passed']=True
                except Exception as exc:row['error']=repr(exc)
                row['seconds']=time.perf_counter()-start
                previous[arm]=(project/'app.py').read_text();(folder/'after.py').write_text(previous[arm])
                books=list(state.rglob('codebook.json'))
                if books:shutil.copyfile(books[0],folder/'book-after.json')
                (folder/'result.json').write_text(json.dumps(row,indent=2));rows.append(row)
                with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                print(json.dumps({k:v for k,v in row.items() if k!='response'}|{k:row.get('response',{}).get(k) for k in ['cache_hit','bound_reuse_hit','exact_reuse_hit','admitted','accounting']}),flush=True)
    (out/'complete.json').write_text(json.dumps(dict(planned=len(allcases)*len(arms)*args.repeats,completed=len(rows),passed=sum(r['passed'] for r in rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--suite',choices=['original','expanded'],default='original')
    args=p.parse_args()
    if args.repeats<1:p.error('positive repeats required')
    main(args)
