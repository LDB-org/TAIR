"""Context-bound plan IDs versus full plan generation and compact generated IDs.

Candidates derive solely from observed source/destination metadata. No learned
codebook; includes out-of-catalog fallback. Classification uses existing engine
logits; binding/execution live in this experimental client, not a new server route.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import time
import uuid

from benchmark_engine_plan import post, tokenize, execute, obj, STRING

SCHEMA = obj({'files': {'type': 'array', 'items': obj({'path': STRING, 'content': STRING}), 'minItems': 1, 'maxItems': 8}})


def bind(files, destinations):
    """Bind available copies without examining the task or expected answer."""
    if set(destinations) - set(files):
        raise ValueError('Missing observed source')
    if len(set(destinations.values())) != len(destinations):
        raise ValueError('Duplicate destination')
    actions = [{'files': [{'path': dst, 'content': files[src]}]} for src, dst in destinations.items()]
    descriptors = [{'copy': [{'source': src, 'destination': dst}]} for src, dst in destinations.items()]
    if len(actions) > 1:
        actions.append({'files': [f for action in actions for f in action['files']]})
        descriptors.append({'copy': [item for desc in descriptors for item in desc['copy']]})
    return actions + [None], descriptors + [None]


def cases():
    cases = []
    for count in [4, 24, 64]:
        files = {'assets/alpha.txt': ''.join(f'alpha row {i:03d}: preserve this literal payload.\n' for i in range(count)),
                 'assets/beta.txt': 'beta: another available source\n'}
        cases.append(dict(name=f'copy_{count}', files=files,
            destinations={'assets/alpha.txt': 'out/alpha.txt', 'assets/beta.txt': 'out/beta.txt'},
            task='Copy assets/alpha.txt exactly to out/alpha.txt. Do not create the beta output.',
            expected={'out/alpha.txt': files['assets/alpha.txt']}, fallback=False))
    files = {'assets/alpha.txt': ''.join(f'alpha entry {i:03d}\n' for i in range(24)),
             'assets/beta.txt': ''.join(f'beta entry {i:03d}\n' for i in range(24))}
    cases.append(dict(name='copy_both', files=files,
        destinations={'assets/alpha.txt': 'out/alpha.txt', 'assets/beta.txt': 'out/beta.txt'},
        task='Copy both assets files into their corresponding out paths, preserving every byte.',
        expected={'out/alpha.txt': files['assets/alpha.txt'], 'out/beta.txt': files['assets/beta.txt']}, fallback=False))
    cases.append(dict(name='novel_content', files={'assets/alpha.txt': 'ordinary source\n', 'assets/beta.txt': 'another source\n'},
        destinations={'assets/alpha.txt': 'out/alpha.txt', 'assets/beta.txt': 'out/beta.txt'},
        task='Create out/novel.txt containing exactly the integers 1 through 5, one integer per line, with a final newline. Do not copy either asset.',
        expected={'out/novel.txt': '1\n2\n3\n4\n5\n'}, fallback=True))
    return cases


def full(url, messages, row):
    before = time.perf_counter()
    tokens = tokenize(url, messages + [{'role': 'user', 'content': 'Return ONLY the complete files JSON. Inline the full literal content of every requested output. Schema: '+json.dumps(SCHEMA)}])
    row['preparation_seconds'] += time.perf_counter()-before
    before = time.perf_counter()
    result = post(url, '/v1/completions', dict(model='/model', prompt=tokens, max_tokens=4096, temperature=0,
        return_token_ids=True, cache_salt=uuid.uuid4().hex, structured_outputs={'json': SCHEMA}))
    row['inference_seconds'] += time.perf_counter()-before
    row['responses'].append(result)
    row['generated_tokens'] += result['usage']['completion_tokens']
    row['logical_input_tokens'] += result['usage']['prompt_tokens']
    choice = result['choices'][0]
    assert choice['finish_reason']=='stop', 'Incomplete generated plan'
    return json.loads(choice['text'])


def attempt(url, arm, case, ids, folder):
    row = dict(arm=arm, case=case['name'], passed=False, generated_tokens=0, controls=0,
               logical_input_tokens=0, preparation_seconds=0., inference_seconds=0., responses=[], fallback=False)
    started = time.perf_counter()
    try:
        actions, descriptors = bind(case['files'], case['destinations'])
        # Shuffle choices independently of desired output; the binder never sees expected.
        order=list(range(len(actions)))
        random.Random(case['name']).shuffle(order)
        actions=[actions[i] for i in order]
        descriptors=[descriptors[i] for i in order]
        messages = [{'role': 'system', 'content': 'Construct a file-writing plan; do not execute it. Preserve exact content when copying. '
            'Available context-bound complete plans are identified by A,B,C,D. null means NONE: the task requires an unlisted plan. '
            'Do not choose a listed plan unless it satisfies the entire request without extra files.\n'
            'Observed sources: '+json.dumps(case['files'])+'\nAvailable plans: '+json.dumps(dict(zip('ABCD',descriptors)))},
            {'role': 'user', 'content': case['task']}]
        row['preparation_seconds'] += time.perf_counter()-started
        if arm=='full':
            arguments=full(url,messages,row)
        else:
            before=time.perf_counter()
            tokens=tokenize(url,messages+[{'role':'user','content':'Return ONLY the single letter identifying the complete plan, or the letter for null if none satisfies the task.'}])
            row['preparation_seconds'] += time.perf_counter()-before
            body=dict(model='/model',prompt=tokens,max_tokens=1,temperature=0,return_token_ids=True,cache_salt=uuid.uuid4().hex)
            if arm=='classify':
                body.update(logprobs=4,logprob_token_ids=ids,return_tokens_as_token_ids=True,vllm_xargs={'openjev_direct_classify':True})
            else:
                body['allowed_token_ids']=ids
            before=time.perf_counter()
            result=post(url,'/v1/completions',body)
            row['inference_seconds'] += time.perf_counter()-before
            row['responses'].append(result)
            row['logical_input_tokens'] += result['usage']['prompt_tokens']
            row['controls'] += int(arm=='classify')
            row['generated_tokens'] += result['usage']['completion_tokens'] if arm=='compact' else 0
            selected=ids.index(result['choices'][0]['token_ids'][0])
            arguments=actions[selected]
            row['selected']=selected
            if arguments is None:
                row['fallback']=True
                arguments=full(url,messages,row)
        row['plan']={'name':'plan','arguments':arguments}
        execute({'kind':'write','arguments':arguments},folder)
        actual={str(f.relative_to(folder)):f.read_text() for f in folder.rglob('*') if f.is_file()}
        assert actual==case['expected'], 'Wrong output content or extra files'
        row['passed']=True
    except Exception as exc:
        row['error']=repr(exc)
    row['total_seconds']=time.perf_counter()-started
    row['inference_requests']=len(row['responses'])
    return row


def main(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    for path in [Path(__file__),Path(__file__).with_name('benchmark_engine_plan.py')]:
        shutil.copyfile(path,out/path.name)
    start=time.perf_counter()
    tokenized=[post(args.url,'/tokenize',dict(model='/model',prompt=c,add_special_tokens=False))['tokens'] for c in 'ABCD']
    assert all(len(t)==1 for t in tokenized)
    ids=[t[0] for t in tokenized]
    setup=time.perf_counter()-start
    (out/'manifest.json').write_text(json.dumps(dict(cases=cases(),ids=ids,repeats=args.repeats,label_setup_seconds=setup,
        timing='Total includes candidate binding, per-attempt tokenization, inference, fallback, external execution and exact-content oracle. Label-ID setup measured separately once.',
        scope='Observed literal copy/batch-copy plus unlisted output. No trained classifier, codebook, full Agent, arbitrary coding or new engine plan route.',
        fairness='All arms see identical observations and candidate descriptions. Compact/classify differ only in ordinary allowed-token sampling versus direct logits control.',
        cache='New namespace for every inference; no cross-request prefix reuse. No warmup excluded.'),indent=2))
    jobs=[(c,a,r) for c in cases() for a in ['full','compact','classify'] for r in range(args.repeats)]
    random.Random(20260920).shuffle(jobs)
    rows=[]
    for index,(case,arm,repeat) in enumerate(jobs):
        folder=out/'artifacts'/str(index);folder.mkdir(parents=True)
        row=attempt(args.url,arm,case,ids,folder);row.update(index=index,repeat=repeat)
        rows.append(row)
        with (out/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps({k:v for k,v in row.items() if k not in ('responses','plan')}),flush=True)
    summary=[]
    for scope in ['all','bound','fallback']:
        names={c['name'] for c in cases() if scope=='all' or c['fallback']==(scope=='fallback')}
        for arm in ['full','compact','classify']:
            group=[r for r in rows if r['arm']==arm and r['case'] in names]
            summary.append(dict(scope=scope,arm=arm,n=len(group),passed=sum(r['passed'] for r in group),
                **{k:sum(r[k] for r in group) for k in ['total_seconds','inference_seconds','preparation_seconds','generated_tokens','controls','inference_requests','logical_input_tokens','fallback']}))
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--repeats',type=int,default=3)
    args=p.parse_args()
    if args.repeats<1:p.error('positive repeats required')
    main(args)
