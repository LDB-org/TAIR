"""Live fused-endpoint budget acceptance, not a task-quality or speed benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/pijit'))
import bridge
from bridge import infer, post, server_plan_budget
from vllm_direct_tools import PLAN_TOTAL_TOKENS


def obj(fields):return dict(type='object',properties=fields,required=list(fields),additionalProperties=False)
def fixed(value):return dict(type='string',enum=[value])


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    for path in [Path(__file__),ROOT/'deploy/vllm_direct_tools.py',ROOT/'integrations/pijit/bridge.py']:
        shutil.copyfile(path,out/path.name)
    assert server_plan_budget(),'Serving endpoint has not enabled per-subtool budgets'
    original_post = bridge.post
    sequence = []
    def recorded_post(route, body):
        if route != '/v1/openjev/toolcall':
            return original_post(route, body)
        headers = {'Content-Type':'application/json'}
        if os.environ.get('PIJIT_API_KEY'):
            headers['Authorization']='Bearer '+os.environ['PIJIT_API_KEY']
        request=urllib.request.Request(os.environ['PIJIT_URL'].rstrip('/')+route,data=json.dumps(body).encode(),headers=headers)
        record={'request':body};sequence.append(record)
        try:
            with urllib.request.urlopen(request,timeout=195) as response:
                record.update(status=response.status,response=json.load(response))
        except urllib.error.HTTPError as error:
            record.update(status=error.code,response=json.load(error))
            raise
        finally:
            (out/'requests.json').write_text(json.dumps(sequence,indent=2))
        return record['response']
    bridge.post=recorded_post
    texts=[''.join(f'{label} row {i:04d}\n' for i in range(220)) for label in ('alpha','bravo')]
    arguments=[dict(path=f'{i}.txt',content=text) for i,text in enumerate(texts)]
    counts=[]
    for args in arguments:
        data=post('/tokenize',dict(model='/model',prompt=json.dumps(args,ensure_ascii=False,separators=(',',':')),add_special_tokens=False))
        counts.append(len(data['tokens']))
    assert max(counts)<=2048 and sum(counts)>2048,counts
    params=[obj({key:fixed(value) for key,value in args.items()}) for args in arguments]
    schema=obj(dict(first=params[0],rest=dict(type='array',minItems=1,maxItems=1,
        items=obj(dict(name=fixed('write'),arguments=params[1])))))
    tool=dict(name='plan',description='Write the two exact text files in one plan.',parameters=schema)
    start=time.perf_counter()
    response=infer([dict(role='user',content='Return the complete two-file plan. Preserve all provided bytes.')],[tool],plan_budget=True)
    row=dict(seconds=time.perf_counter()-start,canonical_argument_tokens=counts,
             max_plan_tokens=PLAN_TOTAL_TOKENS,response=response,
             method='One candidate, constrained exact output. Verifies output budgeting and fused continuation only; no semantic planning claim.')
    (out/'report.json').write_text(json.dumps(row,indent=2))
    actual=response['call']['arguments']
    assert actual==dict(first=arguments[0],rest=[dict(name='write',arguments=arguments[1])])
    assert response['generated_argument_tokens']>2048
    assert response['plan_budget']['argument_tokens']==counts
    assert response['plan_budget']['exceeded_steps']==[] and response['same_engine_session']
    for i,text in enumerate(texts):(out/f'{i}.txt').write_text(text)
    oversized=dict(path='oversized.txt',content=''.join(f'oversized row {i:04d}\n' for i in range(450)))
    expected=len(post('/tokenize',dict(model='/model',prompt=json.dumps(oversized,ensure_ascii=False,separators=(',',':')),add_special_tokens=False))['tokens'])
    assert 2048 < expected < PLAN_TOTAL_TOKENS
    bad=obj(dict(first=obj({key:fixed(value) for key,value in oversized.items()}),rest=dict(type='array',maxItems=0,items={})))
    try:
        infer([dict(role='user',content='Return the exact specified plan.')],
              [dict(name='plan',description='One oversized child',parameters=bad)],plan_budget=True)
    except urllib.error.HTTPError as error:
        assert error.code==422
    else:
        raise AssertionError('Oversized child was accepted')
    failure=sequence[-1]['response']
    assert failure['plan_budget']['argument_tokens']==[expected]
    assert failure['plan_budget']['exceeded_steps']==[0] and 'call' not in failure
    assert failure['usage_complete'] and failure['generated_argument_tokens']>2048
    legacy=infer([dict(role='user',content='Reply OK')],
                 [dict(name='reply_user',description='Reply',parameters=obj(dict(content=fixed('OK'))))])
    assert legacy['call']['arguments']=={'content':'OK'} and legacy['same_engine_session']
    (out/'negative-and-legacy.json').write_text(json.dumps(dict(oversized_child_rejected=True,
        oversized_argument_tokens=expected,rejected_request=failure,legacy_response=legacy),indent=2))
    bridge.post=original_post
    files=sorted(p for p in out.iterdir() if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    print(json.dumps(dict(passed=True,seconds=row['seconds'],generated=response['generated_argument_tokens'],children=counts)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--url',required=True);args=parser.parse_args();os.environ['PIJIT_URL']=args.url
    main(args.out)
