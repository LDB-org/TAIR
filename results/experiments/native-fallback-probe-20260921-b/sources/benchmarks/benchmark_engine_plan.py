"""Bounded plan construction: generated, client split, and existing engine KV continuation.

No service patch, codebook, learned answer, or tool execution inside the engine.
This tests one classified plan family followed by generated arguments, not a
multi-decision engine state machine or a complete conversational Agent.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
import uuid


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


STRING = {'type': 'string'}
SCHEMAS = {
    'read': obj({'paths': {'type': 'array', 'items': STRING, 'minItems': 1, 'maxItems': 8}}),
    'replace': obj({'edits': {'type': 'array', 'minItems': 1, 'maxItems': 8,
        'items': obj({'path': STRING, 'old': STRING, 'new': STRING})}}),
    'write': obj({'files': {'type': 'array', 'minItems': 1, 'maxItems': 8,
        'items': obj({'path': STRING, 'content': STRING})}}),
}
TOOLS = [{'name': name, 'parameters': schema} for name, schema in SCHEMAS.items()]
CATALOG = json.dumps(SCHEMAS)
SYSTEM = ('Construct the next executable plan. Available internal action families and argument schemas: '
          + CATALOG + '\nUse read if the task needs existing file contents not supplied in observations. '
          'Use replace for changes to observed existing files; preserve unrelated text and include all requested edits. '
          'Use write for requested new files. Never invent unobserved existing contents. '
          'Return a complete bounded plan; tools will be executed by the caller only after you finish. '
          'Do not execute tools yourself. Do not add explanations.')


def cases():
    return [
        dict(name='default', task='Set workers default to 7 in app.py.',
             files={'app.py': 'workers = 4\nlabel = "keep"\n'}, observed=True,
             expected={'app.py': 'workers = 7\nlabel = "keep"\n'}, kind='replace'),
        dict(name='two_edits', task='Set workers to 8 in app.py and timeout to 30 in config.py.',
             files={'app.py': 'workers = 4\n', 'config.py': 'timeout = 10\n'}, observed=True,
             expected={'app.py': 'workers = 8\n', 'config.py': 'timeout = 30\n'}, kind='replace'),
        dict(name='function', task='Fix total(values) to sum all values rather than only the first. Preserve the function signature.',
             files={'app.py': 'def total(values):\n    return values[0]\n'}, observed=True,
             expected=None, kind='replace'),
        dict(name='write', task='Create greeting.txt containing exactly "hello" followed by one newline.',
             files={}, observed=True, expected={'greeting.txt': 'hello\n'}, kind='write'),
        dict(name='two_writes', task='Create a.txt containing exactly alpha followed by one newline and b.txt containing exactly beta followed by one newline.',
             files={}, observed=True, expected={'a.txt': 'alpha\n', 'b.txt': 'beta\n'}, kind='write'),
        dict(name='observation_boundary', task='Fix total(values) in app.py to correctly sum all values. The file exists but its contents have not been read.',
             files={'app.py': 'def total(values):\n    return values[0]\n'}, observed=False,
             expected={'app.py': 'def total(values):\n    return values[0]\n'}, kind='read'),
    ]


def post(url, route, body):
    req = urllib.request.Request(url + route, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def tokenize(url, messages):
    return post(url, '/tokenize', dict(model='/model', messages=messages, add_generation_prompt=True,
        chat_template_kwargs={'thinking': False, 'enable_thinking': False}))['tokens']


def prepare(url, case):
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content':
        case['task'] + '\nObserved files: ' + json.dumps(case['files'] if case['observed'] else {})}]
    choose = messages + [{'role': 'user', 'content': 'Select only the action family letter: A=read, B=replace, C=write.'}]
    tails = [[{'role': 'assistant', 'content': code}, {'role': 'user', 'content':
        'Generate ONLY the argument JSON for ' + tool['name'] + '. Schema: ' + json.dumps(tool['parameters'])}]
        for code, tool in zip('ABC', TOOLS)]
    complete = messages + [{'role': 'user', 'content': 'Generate ONLY JSON with kind and arguments, using the selected family and its schema.'}]
    with ThreadPoolExecutor(max_workers=5) as pool:
        tokens = list(pool.map(lambda m: tokenize(url, m), [choose, *[choose + tail for tail in tails], complete]))
    prefix = tokens[0]
    assert all(seq[:len(prefix)] == prefix for seq in tokens[1:4])
    return {'prefix': prefix, 'tails': [seq[len(prefix):] for seq in tokens[1:4]], 'full': tokens[4],
            'messages': messages}


def infer(url, arm, prepared, ids, row):
    base = dict(model='/model', temperature=0, max_tokens=1024, return_token_ids=True, cache_salt=uuid.uuid4().hex)
    if arm == 'engine':
        response = post(url, '/v1/openjev/toolcall', dict(prompt_ids=prepared['prefix'], candidate_ids=ids,
            continuations=prepared['tails'], tools=TOOLS, max_tokens=1024))
        row.update(responses=[response], inference_requests=1, controls=1,
                   generated_tokens=response['generated_argument_tokens'], same_engine_session=response['same_engine_session'])
        return dict(kind=response['call']['name'], arguments=response['call']['arguments'])
    if arm == 'generate':
        schema = {'anyOf': [obj({'kind': {'type': 'string', 'enum': [name]}, 'arguments': spec})
                            for name, spec in SCHEMAS.items()]}
        response = post(url, '/v1/completions', dict(base, prompt=prepared['full'], structured_outputs={'json': schema}))
        row.update(responses=[response], inference_requests=1, controls=0, generated_tokens=response['usage']['completion_tokens'])
        choice = response['choices'][0]
        assert choice['finish_reason'] == 'stop'
        return json.loads(choice['text'])
    first = post(url, '/v1/completions', dict(base, prompt=prepared['prefix'], max_tokens=1, logprobs=3,
        logprob_token_ids=ids, return_tokens_as_token_ids=True, vllm_xargs={'openjev_direct_classify': True}))
    row.update(responses=[first], inference_requests=1, controls=1)
    selected = ids.index(first['choices'][0]['token_ids'][0])
    # Full reconstructed continuation, same token sequence as the fused engine input.
    response = post(url, '/v1/completions', dict(base, prompt=prepared['prefix'] + prepared['tails'][selected],
        structured_outputs={'json': TOOLS[selected]['parameters']}))
    row['responses'].append(response)
    row.update(inference_requests=2, generated_tokens=response['usage']['completion_tokens'])
    choice = response['choices'][0]
    assert choice['finish_reason'] == 'stop'
    return dict(kind=TOOLS[selected]['name'], arguments=json.loads(choice['text']))


def execute(plan, folder):
    """External bounded executor: no arbitrary commands; fail at first invalid step."""
    from jsonschema import validate
    kind, arguments = plan['kind'], plan['arguments']
    validate(arguments, SCHEMAS[kind])
    def path(name):
        target = (folder / name).resolve()
        if not target.is_relative_to(folder.resolve()) or target == folder.resolve():
            raise ValueError('Path outside task directory')
        return target
    if kind == 'read':
        return {name: path(name).read_text() for name in arguments['paths']}
    for item in arguments['edits' if kind == 'replace' else 'files']:
        target = path(item['path'])
        if kind == 'replace':
            source = target.read_text()
            if not item['old'] or source.count(item['old']) != 1:
                raise ValueError('Replacement must match exactly once')
            target.write_text(source.replace(item['old'], item['new'], 1))
        else:
            if target.exists():
                raise ValueError('write only creates new files')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item['content'])
    return None


def verify(case, plan, folder, result):
    assert plan['kind'] == case['kind'], 'Wrong action family'
    actual = {str(p.relative_to(folder)): p.read_text() for p in folder.rglob('*') if p.is_file()}
    if case['expected'] is not None:
        assert actual == case['expected'], 'Artifact mismatch'
    else:
        assert set(actual) == {'app.py'}
        code = 'from app import total; assert total([])==0; assert total([2,-5,8])==5; x=[1,2]; assert total(x)==3; assert x==[1,2]'
        check = subprocess.run([sys.executable, '-B', '-c', code], cwd=folder, capture_output=True, text=True, timeout=5)
        assert check.returncode == 0, check.stderr
    if case['kind'] == 'read':
        assert result == case['files'], 'Required observation missing'


def run(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out / 'benchmark.py')
    ids = [post(args.url, '/tokenize', dict(model='/model', prompt=c, add_special_tokens=False))['tokens'] for c in 'ABC']
    assert all(len(seq) == 1 for seq in ids)
    ids = [seq[0] for seq in ids]
    prepared = {}
    start = time.perf_counter()
    for case in cases():
        prepared[case['name']] = prepare(args.url, case)
    (out / 'inputs.json').write_text(json.dumps(dict(cases=cases(), prepared=prepared, ids=ids), indent=2))
    manifest = dict(repeats=args.repeats, preparation_seconds=time.perf_counter()-start,
        scope='One classified plan family then generated arguments, external execution. Not full Agent or per-field classification.',
        timing='Planning HTTP plus external application/oracle. Tokenization is separately measured offline for all arms; no model warmups excluded.',
        cache='Fresh namespace per attempt. Split stages share a namespace; engine retains its request KV. No codebook.',
        fairness='Same observations, tools and schemas. Output instructions/representation differ for generate; split and engine share exact prepared inputs.',
        model_forward_passes='Not instrumented; API request counts are NOT model forward counts.')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    jobs = [(case, arm, repeat) for case in cases() for arm in ['generate', 'split', 'engine'] for repeat in range(args.repeats)]
    random.Random(20260919).shuffle(jobs)
    rows = []
    for i, (case, arm, repeat) in enumerate(jobs):
        folder = out / 'artifacts' / str(i)
        folder.mkdir(parents=True)
        for name, source in case['files'].items():
            (folder / name).write_text(source)
        row = dict(index=i, case=case['name'], arm=arm, repeat=repeat, passed=False)
        start = time.perf_counter()
        try:
            plan = infer(args.url, arm, prepared[case['name']], ids, row)
            row.update(planning_seconds=time.perf_counter()-start, plan={'name': 'plan', 'arguments': plan})
            result = execute(plan, folder)
            verify(case, plan, folder, result)
            row['passed'] = True
        except Exception as exc:
            row['error'] = repr(exc)
        row['validated_seconds'] = time.perf_counter()-start
        rows.append(row)
        with (out / 'rows.jsonl').open('a') as stream:
            stream.write(json.dumps(row)+'\n')
        print(json.dumps({k: v for k, v in row.items() if k not in ('responses', 'plan')}), flush=True)
    summary = []
    for arm in ['generate', 'split', 'engine']:
        group = [r for r in rows if r['arm'] == arm]
        summary.append(dict(arm=arm, n=len(group), passed=sum(r['passed'] for r in group),
            seconds=sum(r['validated_seconds'] for r in group),
            median_seconds=statistics.median(r['validated_seconds'] for r in group),
            generated_tokens=sum(r.get('generated_tokens', 0) for r in group),
            controls=sum(r.get('controls', 0) for r in group),
            unknown_usage=sum('generated_tokens' not in r for r in group)))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('repeats must be positive')
    run(args)
