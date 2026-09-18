"""Three-arm structural edit regression, including native fallback and execution."""

import os
import argparse
import importlib.util
import json
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load('holdout', ROOT/'benchmarks/evaluate_region_holdout.py')
protocol = load('direct_structural', ROOT/'deploy/direct_structural_protocol.py')
REMOTE = '''import json,sys,time,urllib.request,urllib.error
data=json.load(sys.stdin);begin=time.perf_counter();results=[]
for route,body in data:
 req=urllib.request.Request('http://127.0.0.1:8000'+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=190) as response:results.append({'status':response.status,'body':json.load(response)})
 except urllib.error.HTTPError as error:results.append({'status':error.code,'body':json.loads(error.read())})
print(json.dumps({'seconds':time.perf_counter()-begin,'results':results}))
'''


def remote(host, requests):
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', host, 'python3 -c '+shlex.quote(REMOTE)],
                            input=json.dumps(requests), capture_output=True, text=True, timeout=210)
    result.check_returncode()
    return json.loads(result.stdout)


def prepare(host, source, cases, templates):
    prepared = {}
    tokenize = []
    labels = list('ABCDEF')
    for label in labels:
        tokenize.append(('/tokenize', {'model': '/model', 'prompt': label, 'add_special_tokens': False}))
    for case, task in cases.items():
        allowed = protocol.compact.task_scope(source, task)
        tools = protocol.operation_tools(source, allowed)
        common = 'Edit the supplied file. Make the smallest necessary change and preserve unrelated behavior.\nFILE: port_scanner.py\nSOURCE:\n'+source+'\nTASK: '+task
        payloads = json.loads(json.dumps(templates))
        for payload in payloads.values():
            payload['max_tokens'] = 2048
            payload['messages'][1]['content'] = common
        instruction = protocol.compact.typed_prompt(source, allowed)
        payloads['multi']['messages'][0]['content'] = instruction
        payloads['multi']['structured_outputs'] = {'regex': protocol.compact.typed_grammar(source, allowed)}
        options = '\n'.join(f'{letter}: {tool["name"]}: {tool["description"]}' for letter, tool in zip(labels, tools))
        messages = [{'role': 'system', 'content': instruction+'\nFirst select the operation kind required to satisfy the entire task. Respond ONLY with its option letter.\n'+options},
                    {'role': 'user', 'content': common}]
        index = len(tokenize)
        def add(messages):
            tokenize.append(('/tokenize', {'model': '/model', 'messages': messages,
                'add_generation_prompt': True, 'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}}))
        add(messages)
        for letter, tool in zip(labels, tools):
            add(messages+[{'role': 'assistant', 'content': letter}, {'role': 'user', 'content': protocol.continuation_instruction(tool['name'])}])
        prepared[case] = {'allowed': sorted(allowed), 'tools': tools, 'payloads': payloads, 'tokenize_index': index}
    response = remote(host, tokenize)
    assert all(r['status'] == 200 for r in response['results'])
    ids = [r['body']['tokens'] for r in response['results']]
    assert all(len(t) == 1 for t in ids[:len(labels)])
    for data in prepared.values():
        index = data.pop('tokenize_index')
        prefix = ids[index]
        suffixes = []
        for continuation in ids[index+1:index+1+len(data['tools'])]:
            assert continuation[:len(prefix)] == prefix
            suffixes.append(continuation[len(prefix):])
        data['direct'] = {'prompt_ids': prefix, 'candidate_ids': [t[0] for t in ids[:len(data['tools'])]],
                          'continuations': suffixes, 'tools': data['tools'], 'max_tokens': 2048}
    return prepared


def direct_attempt(folder, data, source, pristine, check, case, host):
    folder.mkdir()
    work = folder/'workspace'
    shutil.copytree(pristine, work)
    (folder/'request.json').write_text(json.dumps(data['direct'], indent=2))
    started = time.perf_counter()
    result = {'passed': False, 'mode': 'direct'}
    try:
        response = remote(host, [('/v1/openjev/toolcall', data['direct'])])
        (folder/'response.json').write_text(json.dumps(response, indent=2))
        result['transport_seconds'] = time.perf_counter()-started
        result['api_seconds'] = response['seconds']
        item = response['results'][0]
        if item['status'] != 200:
            raise ValueError(item['body'])
        body = item['body']
        result['request_id'] = body['request_id']
        selected = body['decision']['index']
        prompt = len(data['direct']['prompt_ids']) + len(data['direct']['continuations'][selected])
        generated = body['generated_argument_tokens']
        control = body['classification_control_records']
        result.update(generated_tokens=generated, control_records=control, selected_operation=body['call']['name'],
                      usage={'prompt_tokens': prompt, 'completion_tokens': generated+control, 'total_tokens': prompt+generated+control})
        updated = protocol.decode(source, protocol.compact.base.digest(source), body['call'], set(data['allowed']))
        (work/'port_scanner.py').write_text(updated)
        result['validation'] = old.b.validate(work, case, check)
        result['passed'] = result['validation']['passed']
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)
    result['seconds'] = time.perf_counter()-started
    (folder/'result.json').write_text(json.dumps(result, indent=2))
    return result


def main(a):
    out = a.out.resolve()
    out.mkdir()
    pristine = out/'pristine'
    shutil.copytree(ROOT/'results/experiments/pi-scanner-20260918-run1/workspace', pristine, ignore=shutil.ignore_patterns('__pycache__'))
    source = (pristine/'port_scanner.py').read_text()
    prior = json.loads((ROOT/'results/experiments/pi-scoped-typed-20260918-a/manifest.json').read_text())
    cases = {key: old.CASES[key] for key in (a.cases or prior['cases'])}
    check = out/'check.py'
    check.write_text(old.CHECK)
    before = {case: old.b.validate(pristine, case, check) for case in cases}
    (out/'before-tests.json').write_text(json.dumps(before, indent=2))
    assert all(not r['passed'] for r in before.values())
    prepared = prepare(a.host, source, cases, prior['templates'])
    (out/'prepared.json').write_text(json.dumps(prepared, indent=2))
    (out/'manifest.json').write_text(json.dumps({'cases': cases, 'repeats': a.repeats, 'seed': 20260922,
        'arms': ['native', 'typed', 'combined'], 'source_sha256': protocol.compact.base.digest(source),
        'fallback': 'At most one native retry from pristine on any protocol/application/test failure',
        'usage': 'Combined prompt = classifier prefix + injected suffix; completion includes one internal control ID; missing usage is never a zero-cost success',
        'timing': 'includes API/SSH, applying edits, task tests, and 17 regressions; payload preparation excluded for every arm',
        'scope': 'Same-project previously tuned regression tasks; not held-out or full agent-loop validation'}, indent=2))
    (out/'sources').mkdir()
    for file in [Path(__file__), ROOT/'deploy/direct_structural_protocol.py', ROOT/'deploy/compact_structural_protocol.py',
                 ROOT/'deploy/structural_edit_protocol.py', ROOT/'deploy/region_edit_protocol.py', ROOT/'benchmarks/evaluate_region_holdout.py',
                 ROOT/'benchmarks/compare_region_edits.py', ROOT/'integrations/pi/apply_edit.mjs', ROOT/'deploy/vllm_direct_tools.py']:
        shutil.copyfile(file, out/'sources'/file.name)
    jobs = [(case, rep) for case in cases for rep in range(a.repeats)]
    rng = random.Random(20260922)
    rng.shuffle(jobs)
    for case, repeat in jobs:
        arms = ['native', 'typed', 'combined']
        rng.shuffle(arms)
        for arm in arms:
            folder = out/f'{case}-{repeat}-{arm}'
            folder.mkdir()
            start = time.perf_counter()
            data = prepared[case]
            attempts = []
            for step, mode in enumerate(['native'] if arm == 'native' else [arm, 'native']):
                path = folder/f'attempt{step}'
                if mode == 'combined':
                    result = direct_attempt(path, data, source, pristine, check, case, a.host)
                else:
                    result = old.attempt(path, data['payloads']['native' if mode == 'native' else 'multi'], source, None,
                        pristine, check, case, 'native' if mode == 'native' else 'multi', a.host,
                        typed_protocol=mode == 'typed', scoped_protocol=mode == 'typed')
                attempts.append(result)
                if result['passed']:
                    break
            row = {'case': case, 'repeat': repeat, 'arm': arm, 'passed': attempts[-1]['passed'],
                   'first_passed': attempts[0]['passed'], 'seconds': time.perf_counter()-start,
                   'attempts': attempts, 'usage_complete': all('usage' in r for r in attempts),
                   'usage': {key: sum(r.get('usage', {}).get(key, 0) for r in attempts)
                             for key in ['prompt_tokens', 'completion_tokens', 'total_tokens']}}
            (folder/'result.json').write_text(json.dumps(row, indent=2))
            with (out/'rows.jsonl').open('a') as output:
                output.write(json.dumps(row)+'\n')
            print(case, repeat, arm, row['passed'], row['first_passed'], row['usage']['completion_tokens'], round(row['seconds'], 2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--host', default=os.environ.get('ENGINE_TOOLCALL_HOST', 'localhost'))
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--cases', nargs='+', choices=list(old.CASES))
    main(p.parse_args())
