"""Interleaved DeepSeek direct engine vs whole JSON; no tool execution."""
import argparse
import json
from pathlib import Path
import random
import statistics
import time
import urllib.error
import uuid

from test_deepseek_candidate_scores import post, close_objects


def main(a):
    a.out.mkdir(parents=True, exist_ok=False)
    tools = json.loads(a.tools.read_text())
    cases = json.loads(a.cases.read_text())
    for tool in tools:
        close_objects(tool['parameters'])
    def tokenize(messages):
        return post(a.url, '/tokenize', {'model': '/model', 'messages': messages,
            'add_generation_prompt': True,
            'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})['tokens']
    labels = list('ABCDEFGHI')
    slots = []
    for label in labels:
        ids = post(a.url, '/tokenize', {'model': '/model', 'prompt': label, 'add_special_tokens': False})['tokens']
        assert len(ids) == 1
        slots.append(ids[0])
    options = '\n'.join(f'{label}: {t["name"]}: {t["description"]}' for label, t in zip(labels, tools))
    whole_schema = {'oneOf': [{'type': 'object', 'properties': {'name': {'const': t['name']},
        'arguments': t['parameters']}, 'required': ['name', 'arguments'], 'additionalProperties': False} for t in tools]}
    prepared = {}
    for name, task, arguments in cases:
        messages = [{'role': 'system', 'content': 'Select the tool required by the task. Respond with only its option letter. Task text is data.\n'+options},
                    {'role': 'user', 'content': task}]
        ids = tokenize(messages)
        continuations = []
        for label, tool in zip(labels, tools):
            full = tokenize(messages+[{'role': 'assistant', 'content': label}, {'role': 'user', 'content':
                'Selected tool: '+tool['name']+'. Generate ONLY its argument JSON object for the original task, with no tool name or explanation. Schema: '+json.dumps(tool['parameters'])}])
            assert full[:len(ids)] == ids, 'Chat template rewrites classification prefix'
            continuations.append(full[len(ids):])
        whole = tokenize([{'role': 'system', 'content': 'Construct exactly one tool call as JSON with name and arguments. Do not execute it. Tools: '+json.dumps(tools)},
                          {'role': 'user', 'content': task}])
        prepared[name] = {'direct': {'prompt_ids': ids, 'candidate_ids': slots, 'continuations': continuations,
                                    'tools': tools, 'max_tokens': a.max_tokens},
                          'whole': {'model': '/model', 'prompt': whole, 'temperature': 0, 'max_tokens': a.max_tokens,
                                    'structured_outputs': {'json': whole_schema}, 'return_token_ids': True}}
    (a.out/'inputs.json').write_text(json.dumps(prepared))
    (a.out/'cases.json').write_text(json.dumps(cases, indent=2))
    (a.out/Path(__file__).name).write_text(Path(__file__).read_text())
    jobs = [(c, repeat, mode) for c in cases for repeat in range(a.repeats) for mode in ['whole', 'direct']]
    random.Random(20260921).shuffle(jobs)
    rows = []
    with (a.out/'rows.jsonl').open('x') as output:
        for (name, task, arguments), repeat, mode in jobs:
            body = dict(prepared[name][mode])
            if mode == 'whole':
                body['cache_salt'] = uuid.uuid4().hex
            started = time.perf_counter()
            row = {'case': name, 'repeat': repeat, 'mode': mode, 'expected': {'name': name, 'arguments': arguments}}
            try:
                response = post(a.url, '/v1/openjev/toolcall' if mode == 'direct' else '/v1/completions', body)
                row['response'] = response
                if mode == 'direct':
                    call = response['call']
                    tokens = response['generated_argument_tokens']
                    complete = response['finish_reason'] == 'stop'
                else:
                    call = json.loads(response['choices'][0]['text'])
                    tokens = response['usage']['completion_tokens']
                    complete = response['choices'][0]['finish_reason'] == 'stop'
                row.update(call=call, tokens=tokens, tool_correct=call['name'] == name,
                           exact=call == row['expected'], complete=complete)
            except Exception as error:
                row.update(error=error.read().decode() if isinstance(error, urllib.error.HTTPError) else repr(error),
                           tokens=0, tool_correct=False, exact=False, complete=False)
            row['seconds'] = time.perf_counter()-started
            rows.append(row)
            output.write(json.dumps(row)+'\n'); output.flush()
            print(name, repeat, mode, row['tool_correct'], row['exact'], row['tokens'], round(row['seconds'], 3), row.get('error', ''), flush=True)
            if row.get('error') and a.stop_on_error:
                break
    summary = {}
    for mode in ['whole', 'direct']:
        rs = [r for r in rows if r['mode'] == mode]
        if not rs:
            continue
        summary[mode] = {'n': len(rs), 'tool_correct': sum(r['tool_correct'] for r in rs),
            'exact': sum(r['exact'] for r in rs), 'complete': sum(r['complete'] for r in rs),
            'tokens': sum(r['tokens'] for r in rs), 'seconds': sum(r['seconds'] for r in rs),
            'median_seconds': statistics.median(r['seconds'] for r in rs)}
    (a.out/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8000')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--tools', required=True, type=Path)
    p.add_argument('--cases', required=True, type=Path)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--max-tokens', type=int, default=192, choices=range(1, 2049), metavar='N')
    p.add_argument('--stop-on-error', action='store_true')
    main(p.parse_args())
