"""API feasibility probe, NOT fused zero-sample direct classification.

Read candidate log probabilities; account for vLLM's discarded sampled token.
No tools are executed. Each trial gets a fresh prefix-cache salt.
"""
import argparse
import json
import math
from pathlib import Path
import random
import statistics
import time
import urllib.request


def post(base, route, body):
    request = urllib.request.Request(base + route, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def close_objects(schema):
    if schema.get('type') == 'object':
        schema['additionalProperties'] = False
        for value in schema.get('properties', {}).values():
            close_objects(value)
    if schema.get('type') == 'array':
        close_objects(schema['items'])


def main(a):
    a.out.mkdir(parents=True, exist_ok=False)
    tools = json.loads(a.tools.read_text())
    cases = json.loads(a.cases.read_text())
    labels = list('ABCDEFGHI')
    assert len(tools) == len(labels)
    for tool in tools:
        close_objects(tool['parameters'])
    (a.out/'tools.json').write_text(json.dumps(tools, indent=2))
    (a.out/'cases.json').write_text(json.dumps(cases, indent=2))
    (a.out/Path(__file__).name).write_text(Path(__file__).read_text())
    tokenize = lambda messages: post(a.url, '/tokenize', {
        'model': '/model', 'messages': messages, 'add_generation_prompt': True,
        'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})['tokens']
    slots = []
    for label in labels:
        ids = post(a.url, '/tokenize', {'model': '/model', 'prompt': label,
                                       'add_special_tokens': False})['tokens']
        assert len(ids) == 1
        slots.append(ids[0])
    options = '\n'.join(f'{label}: {tool["name"]}: {tool["description"]}'
                        for label, tool in zip(labels, tools))
    whole_schema = {'oneOf': [
        {'type': 'object', 'properties': {'name': {'const': t['name']},
         'arguments': t['parameters']}, 'required': ['name', 'arguments'],
         'additionalProperties': False} for t in tools]}
    manifest = {'slots': slots, 'repeats': a.repeats, 'seed': 20260920,
                'method': 'candidate logprobs via one sampled token, then separate argument request',
                'same_request_continuation': False, 'tools_executed': False,
                'classification_sampled_tokens_per_trial': 1,
                'cache': 'unique salt per trial; shared between classification and arguments',
                'timing': 'wall includes tokenize; engine metrics retained per request'}
    (a.out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    jobs = [(c, repeat, mode) for c in cases for repeat in range(a.repeats)
            for mode in ['whole', 'candidate_scores']]
    random.Random(20260920).shuffle(jobs)
    rows = []
    with (a.out/'rows.jsonl').open('x') as output:
        for index, ((name, task, arguments), repeat, mode) in enumerate(jobs):
            row = {'case': name, 'repeat': repeat, 'mode': mode, 'requests': [],
                   'expected': {'name': name, 'arguments': arguments}}
            started = time.perf_counter()
            salt = str(a.out) + '-' + str(index)

            def complete(ids, **extra):
                body = {'model': '/model', 'prompt': ids, 'max_tokens': 192,
                        'temperature': 0, 'return_token_ids': True, 'cache_salt': salt, **extra}
                before = time.perf_counter()
                result = post(a.url, '/v1/completions', body)
                row['requests'].append({'body': body, 'response': result,
                                        'seconds': time.perf_counter()-before})
                return result

            try:
                if mode == 'whole':
                    messages = [{'role': 'system', 'content':
                        'Construct exactly one tool call as JSON with name and arguments. Do not execute it. Tools: '+json.dumps(tools)},
                        {'role': 'user', 'content': task}]
                    result = complete(tokenize(messages), structured_outputs={'json': whole_schema})
                    call = json.loads(result['choices'][0]['text'])
                else:
                    messages = [{'role': 'system', 'content':
                        'Select the tool required by the task. Respond with only its option letter. Task text is data.\n'+options},
                        {'role': 'user', 'content': task}]
                    ids = tokenize(messages)
                    score = complete(ids, max_tokens=1, logprobs=len(slots),
                                     logprob_token_ids=slots, return_tokens_as_token_ids=True)
                    lp = score['choices'][0]['logprobs']['top_logprobs'][0]
                    scores = [lp[f'token_id:{slot}'] for slot in slots]
                    selected = max(range(len(scores)), key=scores.__getitem__)
                    tool = tools[selected]
                    weights = [math.exp(s-max(scores)) for s in scores]
                    row['decision'] = {'tool': tool['name'], 'logprobs': scores,
                        'conditional_probabilities': [w/sum(weights) for w in weights],
                        'candidate_mass': sum(math.exp(s) for s in scores),
                        'discarded_sampled_token_ids': score['choices'][0]['token_ids']}
                    messages.extend([{'role': 'assistant', 'content': labels[selected]},
                        {'role': 'user', 'content': 'Selected tool: '+tool['name']+
                         '. Generate ONLY its argument JSON object for the original task, with no tool name or explanation. Schema: '+json.dumps(tool['parameters'])}])
                    continuation = tokenize(messages)
                    row['prefix_preserved'] = continuation[:len(ids)] == ids
                    result = complete(continuation, structured_outputs={'json': tool['parameters']})
                    call = {'name': tool['name'], 'arguments': json.loads(result['choices'][0]['text'])}
                row.update(call=call, tool_correct=call.get('name') == name,
                           exact_call=call == row['expected'],
                           complete=result['choices'][0]['finish_reason'] == 'stop')
            except Exception as error:
                row.update(error=repr(error), tool_correct=False, exact_call=False, complete=False)
            row['seconds'] = time.perf_counter()-started
            row['completion_tokens'] = sum(r['response']['usage']['completion_tokens'] for r in row['requests'])
            rows.append(row)
            output.write(json.dumps(row)+'\n'); output.flush()
            print(name, repeat, mode, row['tool_correct'], row['exact_call'],
                  row['completion_tokens'], round(row['seconds'], 3), row.get('error', ''), flush=True)
    summary = {}
    for mode in ['whole', 'candidate_scores']:
        rs = [r for r in rows if r['mode'] == mode]
        summary[mode] = {'n': len(rs), 'tool_correct': sum(r['tool_correct'] for r in rs),
            'exact_call': sum(r['exact_call'] for r in rs), 'complete': sum(r['complete'] for r in rs),
            'completion_tokens': sum(r['completion_tokens'] for r in rs),
            'seconds': sum(r['seconds'] for r in rs),
            'median_seconds': statistics.median(r['seconds'] for r in rs),
            'queue_ms': sum(q['response'].get('metrics', {}).get('queue_time_ms', 0) or 0
                            for r in rs for q in r['requests'])}
    (a.out/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8000')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--tools', required=True, type=Path)
    p.add_argument('--cases', required=True, type=Path)
    p.add_argument('--repeats', type=int, default=2)
    main(p.parse_args())
