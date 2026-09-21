"""Ideal complete-action lookup: generate JSON versus classify one action ID."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import statistics
import time
import urllib.request
import uuid


def post(url, route, body):
    request = urllib.request.Request(url + route, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, args.out / 'benchmark.py')
    labels = 'ABCD'
    names = ['alpha', 'bravo', 'charlie', 'delta']
    rng = random.Random(20260918)
    started = time.perf_counter()
    ids = [post(args.url, '/tokenize', {'model': '/model', 'prompt': label,
                                      'add_special_tokens': False})['tokens'] for label in labels]
    assert all(len(tokens) == 1 for tokens in ids)
    ids = [tokens[0] for tokens in ids]
    plans = []
    for size in [32, 128, 512]:
        actions = [{'name': 'write_file', 'arguments': {'path': 'profile.txt',
                    'content': (name + ':0123456789abcdef\n') * (size // 16)}} for name in names]
        for repeat in range(args.repeats):
            order = list(range(4))
            rng.shuffle(order)
            target = repeat % 4
            options = [{'code': labels[i], 'profile': names[j], 'action': actions[j]} for i, j in enumerate(order)]
            common = 'Available complete actions:\n' + json.dumps(options, separators=(',', ':'))
            task = 'Install profile ' + names[target] + '. Select its exact action without changing any field.'
            for arm in ['generate', 'classify']:
                instruction = ('Return ONLY the complete action JSON object, not the profile or code.' if arm == 'generate'
                               else 'Return ONLY the single-letter code of that action.')
                messages = [{'role': 'system', 'content': common + '\n' + instruction}, {'role': 'user', 'content': task}]
                before = time.perf_counter()
                tokens = post(args.url, '/tokenize', {'model': '/model', 'messages': messages,
                    'add_generation_prompt': True, 'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})['tokens']
                body = {'model': '/model', 'prompt': tokens, 'temperature': 0, 'max_tokens': 1024,
                        'return_token_ids': True, 'cache_salt': uuid.uuid4().hex}
                if arm == 'generate' and args.constrain_json:
                    body['structured_outputs'] = {'json': {'type': 'object', 'properties': {
                        'name': {'type': 'string'}, 'arguments': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'content': {'type': 'string'}},
                            'required': ['path', 'content'], 'additionalProperties': False}},
                        'required': ['name', 'arguments'], 'additionalProperties': False}}
                if arm == 'classify':
                    body.update(max_tokens=1, logprobs=4, logprob_token_ids=ids,
                                return_tokens_as_token_ids=True, vllm_xargs={'openjev_direct_classify': True})
                plans.append({'size': size, 'repeat': repeat, 'arm': arm, 'options': options,
                              'expected': actions[target], 'request': body,
                              'tokenize_seconds': time.perf_counter() - before})
    preparation = time.perf_counter() - started
    (args.out / 'plans.json').write_text(json.dumps(plans, indent=2))
    manifest = {'seed': 20260918, 'constrain_json': args.constrain_json, 'repeats': args.repeats, 'preparation_seconds': preparation,
                'scope': 'Ideal explicit named lookup among four complete actions, not natural-language coding ability. Both arms see identical candidates; only output instructions and output mechanism differ. Generated JSON uses a shape-only schema when constrain_json=true; no correct value is forced.',
                'timing': 'HTTP and HTTP+local application measured separately; offline candidate construction and tokenization excluded. Service interval = scheduled-to-first + first-to-last, excludes initial queue, not pure GPU time.',
                'cache': 'Fresh salt per request; no retries; serial randomized interleaving on shared server.',
                'sizes': 'Nominal content sizes; actual strings and generated token counts are recorded.',
                'warmup': 'One call per arm, separately retained, excluded from formal results.'}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    warmups = []
    for arm in ['generate', 'classify']:
        body = dict(next(p['request'] for p in plans if p['arm'] == arm), cache_salt=uuid.uuid4().hex)
        warmups.append({'arm': arm, 'response': post(args.url, '/v1/completions', body)})
    (args.out / 'warmup.json').write_text(json.dumps(warmups, indent=2))
    rng.shuffle(plans)
    rows = []
    for index, plan in enumerate(plans):
        row = {k: plan[k] for k in ('size', 'repeat', 'arm', 'tokenize_seconds')}
        row.update(correct=False, generated_tokens=None, control_records=None)
        before = time.perf_counter()
        try:
            response = post(args.url, '/v1/completions', plan['request'])
            row.update(http_seconds=time.perf_counter() - before, response=response)
            choice = response['choices'][0]
            assert choice.get('finish_reason') in ('stop', 'length'), choice.get('finish_reason')
            if plan['arm'] == 'classify':
                selected = ids.index(choice['token_ids'][0])
                scores = choice['logprobs']['top_logprobs'][0]
                assert selected == max(range(4), key=lambda i: scores[f'token_id:{ids[i]}'])
                action = plan['options'][selected]['action']
                row.update(generated_tokens=0, control_records=1)
            else:
                row.update(generated_tokens=response['usage']['completion_tokens'], control_records=0)
                action = json.loads(choice['text'])
            # Exact action equality gates writes; both paths execute the same local operation.
            assert action == plan['expected'], 'Action mismatch'
            folder = args.out / 'applied' / str(index)
            folder.mkdir(parents=True)
            target = folder / 'profile.txt'
            target.write_text(action['arguments']['content'])
            row['correct'] = target.read_text() == plan['expected']['arguments']['content']
            row['artifact_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        except Exception as error:
            row['error'] = repr(error)
        row['validated_seconds'] = time.perf_counter() - before
        rows.append(row)
        with (args.out / 'rows.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')
        print(json.dumps({k: v for k, v in row.items() if k != 'response'}), flush=True)
    summary = []
    for size in [32, 128, 512]:
        for arm in ['generate', 'classify']:
            group = [r for r in rows if r['size'] == size and r['arm'] == arm]
            service = []
            for row in group:
                metrics = row.get('response', {}).get('metrics') or {}
                values = [metrics.get(k) for k in ['time_to_first_token_ms', 'generation_time_ms']]
                if all(v is not None for v in values):
                    service.append(sum(values) / 1000)
            summary.append({'size': size, 'arm': arm, 'n': len(group), 'correct': sum(r['correct'] for r in group),
                'mean_http_seconds': statistics.mean(r['http_seconds'] for r in group if 'http_seconds' in r),
                'median_http_seconds': statistics.median(r['http_seconds'] for r in group if 'http_seconds' in r),
                'mean_service_seconds': statistics.mean(service) if service else None,
                'service_samples': len(service), 'generated_tokens': sum(r['generated_tokens'] or 0 for r in group),
                'control_records': sum(r['control_records'] or 0 for r in group),
                'unknown_usage': sum(r['generated_tokens'] is None for r in group)})
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--constrain-json', action='store_true')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('repeats must be positive')
    run(args)
