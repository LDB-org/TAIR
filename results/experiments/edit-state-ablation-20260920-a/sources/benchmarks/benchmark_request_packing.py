"""Compare single-step, native multi-tool and a single plan interface. No classifier/cache."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]

def obj(fields):
    return dict(type='object', properties=fields, required=list(fields), additionalProperties=False)

STR = dict(type='string')
PARAMS = {'read': obj({'path': STR}), 'write': obj({'path': STR, 'content': STR}),
          'replace': obj({'path': STR, 'old': STR, 'new': STR}), 'check': obj({})}
DESCRIPTIONS = {'read': 'Read an existing file, returning its contents.',
                'write': 'Write one complete file. Existing nonempty files must be observed first.',
                'replace': 'Replace exactly one matching literal span in observed source.',
                'check': 'Run the delivered unittest tests. Stops execution if tests fail.'}
POLICY = '''Complete the task using only the provided tools. No network, package installs or shell commands.
Use small standard-library Python code. All paths must be among the listed files and relative to the project.
Plan all currently determined operations together when the interface permits. A write and its subsequent check may be planned together because their arguments are known. Do not invent unobserved source. If source must be read, return reads only and wait for their contents before editing. Execution is sequential and stops at the first failure. A passing check after delivering the requested implementation and tests ends the task; do not produce a separate final answer. Failed checks require correction. Importing modules must not perform I/O.'''


def scenarios():
    return [dict(name='new_file_io', files={'file_io.py': ''}, observed=True,
        allowed=['file_io.py','test_file_io.py'],
        task='Create a small file_io.py with read_text(path) returning all UTF-8 text and write_text(path,text,append=False) writing UTF-8, overwriting by default or appending. Accept str and Path. Missing reads raise FileNotFoundError; do not create parent directories. Write test_file_io.py with at least three unittest tests using TemporaryDirectory for Unicode round-trip, overwrite, append and missing-file behavior. Run check. No CLI or extra features.'),
        *[dict(name=name,files={'math_utils.py':'def total(values):\n    return values[0]\n'},observed=observed,
              allowed=['math_utils.py','test_math_utils.py'],
              task='Fix total(values) in math_utils.py to return the sum of all values, including zero for an empty sequence. Preserve its signature and do not mutate the input. Write test_math_utils.py with at least three unittest tests covering empty input, negative/mixed numbers and unchanged input. Run check.')
          for name,observed in [('observed_edit',True),('unobserved_edit',False)]]]


def tools_for(arm):
    if arm=='native_multi':
        return [dict(type='function',function=dict(name=name,description=DESCRIPTIONS[name],parameters=params))
                for name,params in PARAMS.items()]
    steps = [obj({'op': dict(type='string',enum=[name]), **params['properties']}) for name,params in PARAMS.items()]
    return [dict(type='function',function=dict(name='plan',description='Return the next ordered executable operations.',
        parameters=obj({'steps':dict(type='array',minItems=1,maxItems=1 if arm=='single_step' else 8,items={'anyOf':steps})})))]


def crosses_observation_boundary(steps, observed):
    return (any(s['op']=='read' and s['path'] not in observed for s in steps)
            and any(s['op']!='read' for s in steps))


def execute(step, folder, allowed, observed):
    """No arbitrary shell operation; files scoped to the explicit per-task allowlist."""
    from jsonschema import validate
    op = step['op']; args = {k:v for k,v in step.items() if k!='op'}
    validate(args,PARAMS[op])
    if op=='check':
        tests=list(folder.glob('test_*.py'))
        if not tests:raise ValueError('Deliver tests before checking')
        run=subprocess.run([sys.executable,'-B','-m','unittest','discover','-v'],cwd=folder,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=10)
        return dict(ok=run.returncode==0,stdout=run.stdout[-6000:],stderr=run.stderr[-6000:])
    name=args['path'];path=(folder/name).resolve()
    if name not in allowed or not path.is_relative_to(folder.resolve()):raise ValueError('Path not allowed')
    if op=='read':
        source=path.read_text();observed.add(name)
        return dict(ok=True,path=name,content=source)
    if path.exists() and path.read_text() and name not in observed:raise ValueError('Read existing source first')
    if op=='write':path.write_text(args['content'])
    elif op=='replace':
        source=path.read_text()
        if not args['old'] or source.count(args['old'])!=1:raise ValueError('Replacement must match once')
        path.write_text(source.replace(args['old'],args['new'],1))
    observed.add(name)
    return dict(ok=True,path=name)


def verify(case,folder):
    import ast
    tests=[p for p in folder.glob('test_*.py')]
    assert sum(isinstance(n,ast.FunctionDef) and n.name.startswith('test') for p in tests for n in ast.walk(ast.parse(p.read_text())))>=3
    if case['name']=='new_file_io':
        code='''from pathlib import Path
from tempfile import TemporaryDirectory
from file_io import read_text,write_text
with TemporaryDirectory() as d:
 p=Path(d)/'x.txt'
 write_text(p,'雪 café\\n');assert read_text(str(p))=='雪 café\\n'
 write_text(str(p),'new');assert read_text(p)=='new'
 write_text(p,'追加',append=True);assert read_text(p)=='new追加'
 write_text(p,'');assert read_text(p)==''
 try:read_text(Path(d)/'missing')
 except FileNotFoundError:pass
 else:raise AssertionError('Missing file accepted')
 try:write_text(Path(d)/'missing'/'x','x')
 except FileNotFoundError:pass
 else:raise AssertionError('Created parent directory')
'''
    else:
        code='from math_utils import total;assert total([])==0;assert total([2,-5,8])==5;x=[1,2];assert total(x)==3;assert x==[1,2]'
    run=subprocess.run([sys.executable,'-B','-c',code],cwd=folder,capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stderr
    assert {p.name for p in folder.iterdir() if p.is_file()}==set(case['allowed'])


def attempt(url, arm, case, folder, repeat):
    for name,content in case['files'].items():(folder/name).write_text(content)
    known=set(case['files']) if case['observed'] else set()
    user=case['task']+'\nAllowed files: '+json.dumps(case['allowed'])+'\nExisting file names: '+json.dumps(list(case['files']))
    user+='\nObserved source: '+json.dumps(case['files'] if case['observed'] else {})
    messages=[dict(role='system',content=POLICY),dict(role='user',content=user)]
    row=dict(arm=arm,case=case['name'],repeat=repeat,passed=False,requests=[],operations=[],input_tokens=0,output_tokens=0,controls=0,usage_complete=True)
    salt=uuid.uuid4().hex;catalog=tools_for(arm);start=time.perf_counter()
    try:
        for turn in range(8):
            body=dict(model='/model',messages=messages,tools=catalog,tool_choice='required',parallel_tool_calls=arm=='native_multi',
                temperature=0,max_tokens=4096,cache_salt=salt,chat_template_kwargs=dict(thinking=False,enable_thinking=False))
            record=dict(payload=json.loads(json.dumps(body)));row['requests'].append(record)
            begin=time.perf_counter()
            req=urllib.request.Request(url+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=120) as response:data=json.load(response)
            record.update(response=data,seconds=time.perf_counter()-begin)
            row['input_tokens']+=data['usage']['prompt_tokens'];row['output_tokens']+=data['usage']['completion_tokens']
            choice=data['choices'][0]
            if choice['finish_reason'] not in ('stop','tool_calls'):raise ValueError('Incomplete generation: '+choice['finish_reason'])
            message=choice['message'];calls=message.get('tool_calls') or []
            if not calls:raise ValueError('No tool calls')
            if arm!='native_multi' and len(calls)!=1:raise ValueError('Expected one plan call')
            messages.append(dict(role='assistant',content=message.get('content'),tool_calls=calls))
            batches=[]
            from jsonschema import validate
            for call in calls:
                fn=call['function'];args=json.loads(fn['arguments'])
                if arm=='native_multi':
                    validate(args,PARAMS[fn['name']]);steps=[dict(op=fn['name'],**args)]
                else:
                    assert fn['name']=='plan';validate(args,catalog[0]['function']['parameters']);steps=args['steps']
                batches.append((call['id'],steps))
            flattened=[step for _,steps in batches for step in steps]
            if crosses_observation_boundary(flattened,known):raise ValueError('Plan crosses an observation boundary')
            stopped=False;checked=False
            for call_id,steps in batches:
                results=[]
                for step in steps:
                    if stopped:result=dict(ok=False,skipped=True,reason='Previous step failed or check ended this plan')
                    else:
                        try:result=execute(step,folder,case['allowed'],known)
                        except Exception as error:result=dict(ok=False,error=repr(error))
                        row['operations'].append(dict(turn=turn,step=step,result=result))
                    results.append(result)
                    if not result['ok']:stopped=True
                    if step['op']=='check' and result['ok']:checked=True;stopped=True
                messages.append(dict(role='tool',tool_call_id=call_id,content=json.dumps(results)))
            if checked:
                verify(case,folder);row['passed']=True;break
        else:raise ValueError('Eight planning requests exhausted')
    except Exception as error:row['error']=repr(error)
    row['seconds']=time.perf_counter()-start
    row['usage_complete']=all('response' in r and 'usage' in r['response'] for r in row['requests'])
    row['inference_requests']=len(row['requests'])
    return row


def run(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(__file__,out/'benchmark.py')
    cases=scenarios();arms=['single_step','native_multi','single_plan']
    jobs=[(case,arm,r) for r in range(args.repeats) for case in cases for arm in arms]
    random.Random(20260920).shuffle(jobs)
    (out/'manifest.json').write_text(json.dumps(dict(cases=cases,arms=arms,repeats=args.repeats,policy=POLICY,
        schemas={arm:tools_for(arm) for arm in arms},max_tokens=4096,seed=20260920,
        method='Fresh context/cache namespace per attempt, prefix reuse within attempt. One action vs native parallel tools vs one plan with up to eight heterogeneous operations. Same observations and fixed check executor. No final-summary request in any arm. No codebook, classification or engine-internal state machine. Unknown read boundary must yield. Time includes HTTP, external tools and independent oracle; setup excluded.'),indent=2))
    rows=[]
    with tempfile.TemporaryDirectory(prefix='tair-request-packing-') as temp:
        folder=Path(temp)/'project'
        for index,(case,arm,repeat) in enumerate(jobs):
            if folder.exists():shutil.rmtree(folder)
            folder.mkdir()
            row=attempt(args.url,arm,case,folder,repeat);row['index']=index
            dest=out/'attempts'/str(index);dest.mkdir(parents=True)
            shutil.copytree(folder,dest/'project',ignore=shutil.ignore_patterns('__pycache__'))
            (dest/'result.json').write_text(json.dumps(row,indent=2));rows.append(row)
            with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k not in ('requests','operations')}),flush=True)
    def summary(group):
        return dict(attempts=len(group),passed=sum(r['passed'] for r in group),
            **{key:sum(r[key] for r in group) for key in ('seconds','inference_requests','input_tokens','output_tokens','controls')},
            usage_complete=all(r['usage_complete'] for r in group))
    result=dict(all={arm:summary([r for r in rows if r['arm']==arm]) for arm in arms},
                by_case={case['name']:{arm:summary([r for r in rows if r['arm']==arm and r['case']==case['name']]) for arm in arms} for case in cases})
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['all']),flush=True)
    return int(not all(r['passed'] and r['usage_complete'] for r in rows))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=2)
    raise SystemExit(run(p.parse_args()))
