"""Live fused-endpoint budget acceptance, not a task-quality or speed benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/pijit'))
from bridge import infer, post, server_plan_budget
from vllm_direct_tools import PLAN_TOTAL_TOKENS


def obj(fields):return dict(type='object',properties=fields,required=list(fields),additionalProperties=False)
def fixed(value):return dict(type='string',enum=[value])


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    for path in [Path(__file__),ROOT/'deploy/vllm_direct_tools.py',ROOT/'integrations/pijit/bridge.py']:
        shutil.copyfile(path,out/path.name)
    assert server_plan_budget(),'Serving endpoint has not enabled per-subtool budgets'
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
    files=sorted(p for p in out.iterdir() if p.is_file())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    print(json.dumps(dict(passed=True,seconds=row['seconds'],generated=response['generated_argument_tokens'],children=counts)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--url',required=True);args=parser.parse_args();os.environ['PIJIT_URL']=args.url
    main(args.out)
