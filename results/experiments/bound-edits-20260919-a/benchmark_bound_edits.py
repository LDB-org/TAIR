"""Minimal generated edits versus context-bound edit plans, with real execution.

Synthetic Python workspaces; not full Agent or upstream repository evaluation.
"""
import argparse
import ast
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import uuid

from benchmark_engine_plan import post, tokenize, execute, SCHEMAS


def bind(sources):
    """Compile a finite generic operation vocabulary from observed AST constants."""
    singles = []
    for path, source in sorted(sources.items()):
        for node in ast.parse(source).body:
            if (not isinstance(node, ast.Assign) or len(node.targets) != 1
                    or not isinstance(node.targets[0], ast.Name)
                    or node.targets[0].id not in ('workers', 'timeout')
                    or not isinstance(node.value, ast.Constant) or type(node.value.value) is not int):
                continue
            name = node.targets[0].id
            old = ast.get_source_segment(source, node)
            if source.count(old) != 1:
                continue
            edit = {'path': path, 'old': old, 'new': f'{name} = {node.value.value * 2}'}
            singles.append((name, edit))
    plans = [{'edits': [edit]} for _, edit in singles]
    for field in ('workers', 'timeout', None):
        edits = [edit for name, edit in singles if field is None or name == field]
        plan = {'edits': edits}
        if edits and len(edits) <= 8 and plan not in plans:
            plans.append(plan)
    if len(plans) > 15:
        raise ValueError('Candidate capacity exceeded')
    return plans + [None]


def cases():
    result = []
    for name, count, fields, target in [('single', 1, ['workers'], None), ('four_files', 4, ['workers'], None),
                                       ('eight_edits', 4, ['workers', 'timeout'], None), ('one_of_four', 4, ['workers'], 'service_2.py')]:
        sources = {f'service_{i}.py': f'workers = {i+2}\ntimeout = {i+10}\nlabel = "preserve-{i}"\n' for i in range(count)}
        task = 'Double '+ ' and '.join(fields) + (' only in '+target if target else ' in every observed service file') + '. Preserve all other fields and files.'
        result.append(dict(name=name, sources=sources, task=task, fields=fields, target=target, fallback=False))
    result.append(dict(name='new_value', sources={'service_0.py': 'workers = 2\ntimeout = 10\nlabel = "preserve-0"\n'},
        task='Set workers to 7 in service_0.py. Preserve all other fields.', fields=['workers'], target=None, value=7, fallback=True))
    result.append(dict(name='new_code', sources={'app.py': 'def total(values):\n    return values[0]\n'},
        task='Fix total(values) in app.py to sum all values, including an empty list. Preserve the signature.', fallback=True))
    return result


def verify(case, folder):
    actual = {str(p.relative_to(folder)): p.read_text() for p in folder.rglob('*') if p.is_file()}
    assert set(actual) == set(case['sources']), 'File set changed'
    if case['name'] == 'new_code':
        command = 'from app import total; assert total([])==0; assert total([2,-5,8])==5; x=[1,2]; assert total(x)==3; assert x==[1,2]'
        result = subprocess.run([sys.executable, '-B', '-c', command], cwd=folder, capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stderr
        return
    for path, source in case['sources'].items():
        expected = ast.parse(source)
        if case['target'] is None or case['target'] == path:
            for node in expected.body:
                if isinstance(node, ast.Assign) and node.targets[0].id in case['fields']:
                    node.value = ast.Constant(case.get('value', node.value.value * 2))
        assert ast.dump(ast.parse(actual[path])) == ast.dump(expected), 'Unrequested AST change or wrong value'
        compile(actual[path], path, 'exec')


def infer(url, messages, ids, candidates, arm, row):
    if arm == 'generate':
        instruction = 'Return ONLY minimal replacement edits as JSON. Do not rewrite whole files. Schema: '+json.dumps(SCHEMAS['replace'])
    else:
        instruction = 'Return ONLY the single letter of the candidate satisfying the ENTIRE request. Select null if no candidate fully satisfies it. Do not select an approximate candidate.'
    before = time.perf_counter()
    tokens = tokenize(url, messages+[{'role':'user','content':instruction}])
    row['preparation_seconds'] += time.perf_counter()-before
    body = dict(model='/model',prompt=tokens,max_tokens=2048 if arm=='generate' else 1,
                temperature=0,return_token_ids=True,cache_salt=uuid.uuid4().hex)
    if arm=='generate': body['structured_outputs']={'json':SCHEMAS['replace']}
    elif arm=='compact': body['allowed_token_ids']=ids
    else: body.update(logprobs=len(ids),logprob_token_ids=ids,return_tokens_as_token_ids=True,vllm_xargs={'openjev_direct_classify':True})
    before=time.perf_counter()
    response=post(url,'/v1/completions',body)
    row['inference_seconds']+=time.perf_counter()-before
    row['responses'].append(response)
    row['logical_input_tokens']+=response['usage']['prompt_tokens']
    row['generated_tokens']+=response['usage']['completion_tokens'] if arm!='classify' else 0
    row['controls']+=int(arm=='classify')
    choice=response['choices'][0]
    if arm=='generate':
        assert choice['finish_reason']=='stop', 'Truncated edit'
        return json.loads(choice['text'])
    selected=ids.index(choice['token_ids'][0]);row['selected']=selected
    arguments=candidates[selected]
    if arguments is None:
        row['fallback']=True
        return infer(url,messages,ids,candidates,'generate',row)
    return arguments


def main(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ['benchmark_bound_edits.py','benchmark_engine_plan.py']:
        shutil.copyfile(Path(__file__).with_name(name),out/name)
    jobs=[(case,arm,repeat) for case in cases() for arm in ['generate','compact','classify'] for repeat in range(args.repeats)]
    random.Random(20260921).shuffle(jobs)
    start=time.perf_counter()
    ids=[post(args.url,'/tokenize',dict(model='/model',prompt=c,add_special_tokens=False))['tokens'] for c in 'ABCDEFGHIJKLMNOP']
    assert all(len(t)==1 for t in ids);ids=[t[0] for t in ids]
    (out/'manifest.json').write_text(json.dumps(dict(cases=cases(),label_setup_seconds=time.perf_counter()-start,
        repeats=args.repeats,scope='Synthetic Python edits, one planning/execution stage; no complete Agent.',
        timing='Includes AST candidate binding, tokenization, inference, fallback, edit execution and independent oracle; excludes initial fixture creation and one-time label setup.',
        cache='Fresh request salt; no learned codebook or cross-request prefix reuse.',
        representation='Generator produces minimal edits, not whole-file rewrites. All arms see same sources and complete candidate edits. Binder does not receive task or expected answer.'),indent=2))
    rows=[]
    for index,(case,arm,repeat) in enumerate(jobs):
        folder=out/'artifacts'/str(index);folder.mkdir(parents=True)
        for path,source in case['sources'].items():(folder/path).write_text(source)
        row=dict(index=index,case=case['name'],arm=arm,repeat=repeat,passed=False,fallback=False,
            responses=[],generated_tokens=0,controls=0,logical_input_tokens=0,preparation_seconds=0.,inference_seconds=0.)
        start=time.perf_counter()
        try:
            candidates=bind(case['sources']);random.Random(case['name']).shuffle(candidates)
            messages=[{'role':'system','content':'Construct a plan of Python source edits without executing it. Candidates are complete plans compiled from observed sources. null means an unlisted plan is needed.\nSources: '+json.dumps(case['sources'])+'\nCandidates: '+json.dumps(dict(zip('ABCDEFGHIJKLMNOP',candidates)))},
                {'role':'user','content':case['task']}]
            row['preparation_seconds']+=time.perf_counter()-start
            arguments=infer(args.url,messages,ids[:len(candidates)],candidates,arm,row)
            row['plan']={'name':'plan','arguments':arguments}
            execute({'kind':'replace','arguments':arguments},folder)
            verify(case,folder);row['passed']=True
        except Exception as exc:row['error']=repr(exc)
        row['total_seconds']=time.perf_counter()-start
        row['inference_requests']=len(row['responses'])
        rows.append(row)
        with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps({k:v for k,v in row.items() if k not in ('responses','plan')}),flush=True)
    summary=[]
    for scope in ['all','bound','fallback']:
        names={c['name'] for c in cases() if scope=='all' or c['fallback']==(scope=='fallback')}
        for arm in ['generate','compact','classify']:
            group=[r for r in rows if r['case'] in names and r['arm']==arm]
            summary.append(dict(scope=scope,arm=arm,n=len(group),passed=sum(r['passed'] for r in group),
                **{k:sum(r[k] for r in group) for k in ['total_seconds','preparation_seconds','inference_seconds','generated_tokens','controls','inference_requests','logical_input_tokens','fallback']}))
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.repeats<1:parser.error('positive repeats required')
    main(args)
