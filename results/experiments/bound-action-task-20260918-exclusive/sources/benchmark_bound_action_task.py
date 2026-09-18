"""Bounded complete-task comparison: stock Pi versus one-shot bound actions."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = load('preset_benchmark', ROOT / 'benchmarks/compare_pijit_presets.py')
preset = load('preset', ROOT / 'deploy/preset_edits.py')
http = load('ideal_http', ROOT / 'benchmarks/benchmark_ideal_classification.py')


def bound(project, folder, value, arm, rng):
    # Start before reading source, binding candidates, or tokenizing any prompt.
    started = time.perf_counter()
    row = {'arm': arm, 'value': value, 'passed': False}
    try:
        source = (project / 'app.py').read_text()
        tree = ast.parse(source)
        defaults = [ast.literal_eval(k.value) for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == 'add_argument'
                    and any(isinstance(a, ast.Constant) and a.value == '--workers' for a in n.args)
                    for k in n.keywords if k.arg == 'default']
        assert len(defaults) == 1
        actions = [{'name': 'set_cli_default', 'arguments': {'path': 'app.py', 'option': '--workers',
                   'expected_default': defaults[0], 'value': n}} for n in [2, 4, 6, 8, 10]] + [None]
        rng.shuffle(actions)
        labels = 'ABCDEF'
        task = f'Read app.py, then change the --workers default to {value}. Preserve explicit overrides and all unrelated code. After a successful edit, reply DONE.'
        instruction = ('Return only the letter of the complete action that satisfies the task. Select null if none applies.'
                       if arm == 'classify' else 'Return only the complete action JSON that satisfies the task, or null if none applies.')
        messages = [{'role': 'system', 'content': 'The runner already reads the source, applies the selected edit, verifies behavior, and replies DONE. Your only decision is which edit sets the requested default.\n' + instruction + '\nCandidates:\n' +
                     '\n'.join(l + ': ' + json.dumps(a) for l, a in zip(labels, actions))},
                    {'role': 'user', 'content': 'SOURCE app.py:\n' + source + '\nTASK:\n' + task}]
        url = os.environ['PIJIT_URL']
        tokens = http.post(url, '/tokenize', {'model': '/model', 'messages': messages,
            'add_generation_prompt': True, 'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}})['tokens']
        request = {'model': '/model', 'prompt': tokens, 'temperature': 0, 'max_tokens': 256,
                   'cache_salt': uuid.uuid4().hex, 'return_token_ids': True}
        if arm == 'classify':
            ids = [http.post(url, '/tokenize', {'model': '/model', 'prompt': l, 'add_special_tokens': False})['tokens'] for l in labels]
            assert all(len(i) == 1 for i in ids)
            ids = [i[0] for i in ids]
            request.update(max_tokens=1, logprobs=6, logprob_token_ids=ids, return_tokens_as_token_ids=True,
                           vllm_xargs={'openjev_direct_classify': True})
        else:
            request['structured_outputs'] = {'json': {'anyOf': [{'type': 'null'}, {'type': 'object',
                'properties': {'name': {'type': 'string'}, 'arguments': preset.TOOL['parameters']},
                'required': ['name', 'arguments'], 'additionalProperties': False}]}}
        row['preparation_seconds'] = time.perf_counter() - started
        (folder / 'plan.json').write_text(json.dumps({'actions': actions, 'messages': messages, 'request': request}, indent=2))
        begin = time.perf_counter()
        response = http.post(url, '/v1/completions', request)
        row.update(http_seconds=time.perf_counter() - begin, response=response,
                   generated_tokens=0 if arm == 'classify' else response['usage']['completion_tokens'],
                   control_records=int(arm == 'classify'))
        choice = response['choices'][0]
        if arm == 'classify':
            selected = ids.index(choice['token_ids'][0])
            scores = choice['logprobs']['top_logprobs'][0]
            assert selected == max(range(6), key=lambda i: scores[f'token_id:{ids[i]}'])
            action = actions[selected]
        else:
            action = json.loads(choice['text'])
        assert action in actions and action is not None, 'Unknown or rejected action'
        args = action['arguments']
        changed = preset.set_cli_default(source, args['option'], args['expected_default'], args['value'])
        assert (project / 'app.py').read_text() == source, 'Source changed'
        (project / 'app.py').write_text(changed)
        # Same independent AST/behavior oracle used for native Pi.
        expected = baseline.SOURCE.replace('default=4', f'default={value}')
        check = ('import ast\nfrom pathlib import Path\n'
                 f'assert ast.dump(ast.parse(Path("app.py").read_text())) == {ast.dump(ast.parse(expected))!r}\n'
                 'import app\np=app.build_parser()\n'
                 f'assert p.parse_args([]).workers == {value}\n'
                 'assert p.parse_args(["--workers", "23"]).workers == 23\n')
        (project / 'verify.py').write_text(check)
        checked = subprocess.run([sys.executable, '-B', 'verify.py'], cwd=project, capture_output=True, text=True, timeout=15)
        row.update(passed=checked.returncode == 0, validation_stderr=checked.stderr,
                   generated_tokens=0 if arm == 'classify' else response['usage']['completion_tokens'],
                   control_records=int(arm == 'classify'))
        if row['passed']:
            row['reply'] = 'DONE'  # Deterministic completion, no additional inference.
        else:
            (project / 'app.py').write_text(source)
    except Exception as error:
        row['error'] = repr(error)
    row['validated_seconds'] = time.perf_counter() - started
    (folder / 'after.py').write_bytes((project / 'app.py').read_bytes())
    (folder / 'result.json').write_text(json.dumps(row, indent=2))
    return row


def main(args):
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    (out / 'sources').mkdir()
    for f in [Path(__file__), ROOT/'benchmarks/compare_pijit_presets.py', ROOT/'benchmarks/native_pi_trace.ts',
              ROOT/'benchmarks/benchmark_ideal_classification.py', ROOT/'deploy/preset_edits.py']:
        shutil.copyfile(f, out/'sources'/f.name)
    (out/'manifest.json').write_text(json.dumps({'scope': 'Bounded argparse --workers integer default fixture. Six prebound candidates including NONE, values fixed independently of expected answer. Not a general Agent.',
        'arms': ['native', 'generate', 'classify'], 'repeats': args.repeats, 'values': [6,8], 'seed': 20260919,
        'timing': 'Bound arms include source read, binding, cold tokenization, model HTTP, local execution and independent behavior validation. Native includes Pi startup/read/edit/reply and same final oracle. Bound arms use deterministic DONE and one model call; native remains general Pi loop. Bound Python interpreter/import startup excluded. No retries or warm-up; all samples retained.',
        'causality': 'generate versus classify isolates output mechanism with same specialized workflow; native comparison also changes orchestration. Six remote label tokenizer calls per classification deliberately included, no persistent label cache.',
        'server': 'Existing shared patched vLLM, max-num-seqs 4; no restart/configuration change.'},indent=2))
    rng=random.Random(20260919)
    for repeat in range(args.repeats):
        for value in [6,8]:
            arms=['native','generate','classify'];rng.shuffle(arms)
            # Same shuffled action ordering within a matched generate/classify pair.
            seed=rng.randrange(2**32)
            for arm in arms:
                folder=out/f'{repeat}-{value}-{arm}';folder.mkdir()
                project=folder/'project';project.mkdir();(project/'app.py').write_text(baseline.SOURCE)
                if arm=='native':
                    row=baseline.attempt(project,folder/'state',folder,arm,value,150)
                else:
                    row=bound(project,folder,value,arm,random.Random(seed))
                row.update(repeat=repeat)
                with (out/'rows.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
                print(json.dumps({k:row[k] for k in ['arm','value','repeat','passed','validated_seconds']}),flush=True)
                if (row.get('error') and 'response' not in row) or (arm == 'native' and not row.get('finished')):
                    (out/'aborted.json').write_text(json.dumps({'reason': 'Request/runtime failure; stop before more requests', 'arm': arm, 'repeat': repeat, 'value': value}))
                    return


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--repeats',type=int,default=2)
    main(parser.parse_args())
