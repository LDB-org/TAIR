"""Bounded whole-edit classification probe; no fallback, no free argument generation."""

import os
import ast
import importlib.util
import json
from pathlib import Path
import random
import re
import shutil
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('benchmark', ROOT/'benchmarks/evaluate_direct_structural.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
HOST = os.environ.get('TAIR_ENGINE_HOST', os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost'))


def candidates(source, task, allowed):
    aliases = b.protocol.compact.scoped_selectors(source, allowed)
    nodes = b.protocol.compact.base.catalogue(source)
    result = []
    for target, key in aliases['C'].items():
        node = nodes[key]
        numbers = {int(n) for n in re.findall(r'\b\d+\b', task)}
        numbers.update(n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and type(n.value) is int)
        for slot in b.protocol.compact.keyword_slots(node):
            kind = b.protocol.compact.value_kind(node, slot)
            values = [False, True] if kind == 'bool' else sorted(numbers) if kind == 'int' else [None] if kind == 'null' else []
            for value in values:
                result.append([['kw', target, slot, value]])
    result.append(None)
    assert 1 < len(result) <= 26
    return result


def main(out):
    out.mkdir()
    prior = ROOT/'results/experiments/pi-combined-structural-20260918-a'
    prepared = json.loads((prior/'prepared.json').read_text())
    source = (prior/'pristine/port_scanner.py').read_text()
    pristine = out/'pristine'; shutil.copytree(prior/'pristine', pristine)
    check = out/'check.py'; check.write_text(b.old.CHECK)
    cases = ['default_workers_six', 'json_unicode', 'json_no_nan']
    labels = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    tokenized = b.remote(HOST, [('/tokenize', {'model':'/model','prompt':l,'add_special_tokens':False}) for l in labels])
    label_ids = [r['body']['tokens'][0] for r in tokenized['results']]
    assert all(r['status']==200 and len(r['body']['tokens'])==1 for r in tokenized['results'])
    plans = {}
    rng = random.Random(20260923)
    requests = []
    for case in cases:
        for rep in range(2):
            choices = candidates(source,b.old.CASES[case],set(prepared[case]['allowed']))
            rng.shuffle(choices)
            options = '\n'.join(l+': '+(json.dumps(c,separators=(',',':')) if c else 'NONE: no candidate satisfies the entire task') for l,c in zip(labels,choices))
            messages = [{'role':'system','content':'Choose the single complete edit that satisfies the task. Each kw tuple sets a keyword argument on a source call. Return only its letter. Do not generate code.\n'+options},prepared[case]['payloads']['native']['messages'][1]]
            requests.append(('/tokenize',{'model':'/model','messages':messages,'add_generation_prompt':True,'chat_template_kwargs':{'thinking':False,'enable_thinking':False}}))
            plans[f'{case}-{rep}'] = {'choices':choices,'messages':messages}
    tokens=b.remote(HOST,requests)['results']
    for plan,item in zip(plans.values(),tokens):
        assert item['status']==200
        plan['request']={'model':'/model','prompt':item['body']['tokens'],'temperature':0,'max_tokens':1,
            'logprobs':len(plan['choices']),'logprob_token_ids':label_ids[:len(plan['choices'])],
            'return_tokens_as_token_ids':True,'return_token_ids':True,
            'vllm_xargs':{'openjev_direct_classify':True},'cache_salt':uuid.uuid4().hex}
    (out/'plans.json').write_text(json.dumps(plans,indent=2))
    (out/'manifest.json').write_text(json.dumps({'cases':cases,'repeats':2,'seed':20260923,'scope':'Only finite integer/bool/null keyword edits; source/task-derived candidates plus NONE, no free argument generation. Candidate orders reshuffled each repetition. No fallback. All arms execute identical task checks and 17 regressions. Full-edit candidate list is not general code generation. Timing includes shared-server queues.','classification':'Existing V2 direct sampler hook via vllm_xargs; one control output, verify audit logs before claiming no sampling.'},indent=2))
    (out/'sources').mkdir()
    for f in [Path(__file__),ROOT/'benchmarks/evaluate_direct_structural.py',ROOT/'deploy/vllm_direct_tools.py']:
        shutil.copyfile(f,out/'sources'/f.name)
    jobs=[(c,r,a) for c in cases for r in range(2) for a in ['all_classification','typed','combined']];rng.shuffle(jobs)
    for case,rep,arm in jobs:
        folder=out/f'{case}-{rep}-{arm}'
        if arm=='combined':
            result=b.direct_attempt(folder,prepared[case],source,pristine,check,case,HOST)
        elif arm=='typed':
            result=b.old.attempt(folder,prepared[case]['payloads']['multi'],source,None,pristine,check,case,'multi',HOST,typed_protocol=True,scoped_protocol=True)
        else:
            folder.mkdir(); work=folder/'workspace';shutil.copytree(pristine,work)
            plan=plans[f'{case}-{rep}']; started=time.perf_counter();result={'passed':False}
            (folder/'request.json').write_text(json.dumps(plan['request'],indent=2))
            try:
                response=b.remote(HOST,[('/v1/completions',plan['request'])]);(folder/'response.json').write_text(json.dumps(response,indent=2))
                result['transport_seconds']=time.perf_counter()-started
                item=response['results'][0];assert item['status']==200,item
                body=item['body'];choice=body['choices'][0]
                result.update(usage=body['usage'],metrics=body.get('metrics'),request_id=body['id'])
                scores=choice['logprobs']['top_logprobs'][0]
                values=[scores[f'token_id:{i}'] for i in plan['request']['logprob_token_ids']]
                selected=max(range(len(values)),key=values.__getitem__)
                assert choice['token_ids']==[plan['request']['logprob_token_ids'][selected]]
                edits=plan['choices'][selected];result.update(selected=selected,edits=edits,logprobs=values)
                if edits is None:raise ValueError('No candidate selected')
                changed=b.protocol.compact.typed_decode(source,b.protocol.compact.base.digest(source),json.dumps(edits,separators=(',',':')),'stop',set(prepared[case]['allowed']))
                (work/'port_scanner.py').write_text(changed)
                result['validation']=b.old.b.validate(work,case,check);result['passed']=result['validation']['passed']
            except Exception as error:result['error']=repr(error)
            result['seconds']=time.perf_counter()-started
            (folder/'result.json').write_text(json.dumps(result,indent=2))
        row={'case':case,'repeat':rep,'arm':arm,**result}
        with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(case,rep,arm,result['passed'],result.get('usage'),round(result['seconds'],2),result.get('error',''),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out.resolve())
