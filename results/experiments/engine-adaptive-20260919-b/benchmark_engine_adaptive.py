"""Cold-to-warm automatic admission and fused engine entry selection, C1."""
import argparse
import json
from pathlib import Path
import random
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deploy'))
from adaptive_plan import PlanBook, infer, execute_and_learn, plan_schema, post
from benchmark_adaptive_plan import check_module

CONTRACTS = {
    'utf8': 'Provide read_text(path) and write_text(path,text,*,append=False), UTF-8 text, str or Path paths. Read the whole file. Write overwrites by default or appends on append=True; create missing files, but do not create parent directories. Missing reads raise FileNotFoundError.',
    'utf16': 'Provide read_text(path) and write_text(path,text,*,append=False), UTF-16 (not UTF-8) text, str or Path paths. Read the whole file. Overwrite by default, append when requested. Do not create parent directories. Missing reads raise FileNotFoundError.',
    'binary': 'Provide read_bytes(path) and write_bytes(path,data,*,append=False), arbitrary binary bytes including invalid UTF-8. str or Path paths. Read entire file, overwrite by default or append when requested. No automatic parent directories. Missing reads raise FileNotFoundError.',
    'exclusive': 'Provide read_text(path) and write_text(path,text), UTF-8. Read entire file. Write creates a new file; if it exists, raise FileExistsError and preserve every byte. Never overwrite or append. Accept str or Path. Do not create parents. Missing reads raise FileNotFoundError.',
    'parents': 'Provide read_text(path) and write_text(path,text,*,append=False), UTF-8, str or Path. Read entire file, overwrite by default or append when requested. Writing MUST automatically create missing parent directories, including nested parents. Missing reads raise FileNotFoundError.',
}
JOBS = [
    ('utf8_cold', {'text_io.py': 'utf8'}),
    ('utf8_warm', {'helpers/local_io.py': 'utf8'}),
    ('utf16_cold', {'text_io.py': 'utf16'}),
    ('utf16_warm', {'utf16_io.py': 'utf16'}),
    ('mixed_new_binary', {'text_io.py': 'utf8', 'binary_io.py': 'binary'}),
    ('binary_warm', {'binary_io.py': 'binary'}),
    ('exclusive_cold', {'text_io.py': 'exclusive'}),
    ('exclusive_warm', {'exclusive_io.py': 'exclusive'}),
    ('parents_cold', {'text_io.py': 'parents'}),
    ('parents_warm', {'nested_io.py': 'parents'}),
]


def verify(path, contract):
    kind = next(k for k, value in CONTRACTS.items() if value == contract)
    check_module(path, kind)
    return 'Caller-supplied behavior suite v1: ' + kind


def naive(url, task, contracts):
    body = dict(model='/model', temperature=0, max_tokens=2048, cache_salt=uuid.uuid4().hex,
                chat_template_kwargs=dict(thinking=False, enable_thinking=False),
                messages=[dict(role='system', content='Return one complete plan for all requested Python modules. Generate complete source. No shell, network, tests, extra files, explanations or import-time I/O.'),
                          dict(role='user', content=json.dumps(dict(task=task, output_contracts=contracts)))],
                tools=[dict(type='function', function=dict(name='plan', parameters=plan_schema(contracts)))],
                tool_choice=dict(type='function', function=dict(name='plan')), parallel_tool_calls=False)
    start = time.perf_counter()
    response = post(url, '/v1/chat/completions', body)
    choice = response['choices'][0]
    assert choice['finish_reason'] in ('stop', 'tool_calls')
    calls = choice['message']['tool_calls']
    assert len(calls) == 1 and calls[0]['function']['name'] == 'plan'
    arguments = json.loads(calls[0]['function']['arguments'])
    from jsonschema import validate
    validate(arguments, plan_schema(contracts))
    return dict(plan=dict(name='plan', arguments=arguments), response=response, request=body,
                preparation_seconds=0., inference_seconds=time.perf_counter()-start,
                logical_input_tokens=response['usage']['prompt_tokens'], generated_tokens=response['usage']['completion_tokens'],
                controls=0, inference_requests=1, selected_entry=None)


def run(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    for source in [Path(__file__), ROOT/'deploy/adaptive_plan.py', ROOT/'benchmarks/benchmark_adaptive_plan.py']:
        shutil.copyfile(source, out/source.name)
    (out/'manifest.json').write_text(json.dumps(dict(repeats=args.repeats, jobs=JOBS, contracts=CONTRACTS,
        method='Two arms, sequential curriculum per independent empty book and repeat; randomized arm order per stage. No warmup or retries. C1. Same 2048 output budget. Engine directly selects one stored entry or GENERATE and continues in the same engine session. Empty book still classifies GENERATE. Entire plan must pass caller-supplied behavioral checks before automatic admission. Baseline also validates and saves generated artifacts but never receives a catalog.',
        timing='Total includes on-demand tokenization/preparation, one inference HTTP, execution, behavioral verification and disk admission. Inference and preparation separately reported. Tokenization HTTP calls do not run model inference. Logical input counts engine prefix plus selected continuation, excluding unused candidate tails and control record.'), indent=2))
    rows = []
    def recorded_transport(url, route, body):
        if route == '/v1/openjev/toolcall':
            (folder/'engine-request.json').write_text(json.dumps(body, indent=2))
        response = post(url, route, body)
        if route == '/v1/openjev/toolcall':
            (folder/'engine-raw.json').write_text(json.dumps(dict(request=body, response=response), indent=2))
        return response
    for repeat in range(args.repeats):
        for stage, (name, kinds) in enumerate(JOBS):
            arms = ['naive', 'engine']
            random.Random(20260922 + repeat*100 + stage).shuffle(arms)
            for arm in arms:
                folder = out/'attempts'/f'{repeat}-{stage}-{arm}'
                folder.mkdir(parents=True)
                book = PlanBook(out/'books'/f'{repeat}-{arm}.json')
                before = book.load()
                (folder/'book-before.json').write_text(json.dumps(before, indent=2))
                contracts = {path: CONTRACTS[kind] for path, kind in kinds.items()}
                task = 'Create exactly these modules: ' + ', '.join(kinds)
                row = dict(repeat=repeat, stage=stage, case=name, arm=arm, passed=False, book_before=len(before))
                start = time.perf_counter()
                try:
                    actual = infer(args.url, task, contracts, book, recorded_transport) if arm == 'engine' else naive(args.url, task, contracts)
                    row.update(actual)
                    row['admitted'] = execute_and_learn(actual, contracts, folder/'project', book, verify)
                    row['reuse_steps'] = sum(s['op']=='reuse' for s in actual['plan']['arguments']['steps'])
                    row['passed'] = True
                except Exception as error:
                    row['error'] = repr(error)
                row.update(seconds=time.perf_counter()-start, book_after=len(book.load()))
                (folder/'book-after.json').write_text(json.dumps(book.load(), indent=2))
                (folder/'result.json').write_text(json.dumps(row, indent=2))
                rows.append(row)
                with (out/'rows.jsonl').open('a') as stream:
                    stream.write(json.dumps(row)+'\n')
                print(json.dumps({k:v for k,v in row.items() if k not in ('request','response','plan')}), flush=True)
    totals = {}
    for arm in ['naive', 'engine']:
        selected = [r for r in rows if r['arm']==arm]
        totals[arm] = dict(attempts=len(selected), passed=sum(r['passed'] for r in selected),
            usage_complete=all('generated_tokens' in r for r in selected),
            **{k:sum(r.get(k,0) for r in selected) for k in ['seconds','preparation_seconds','inference_seconds','logical_input_tokens','generated_tokens','controls','inference_requests','reuse_steps']})
    (out/'summary.json').write_text(json.dumps(totals, indent=2))
    print(json.dumps(totals), flush=True)
    return int(not all(r['passed'] for r in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=2)
    raise SystemExit(run(parser.parse_args()))
