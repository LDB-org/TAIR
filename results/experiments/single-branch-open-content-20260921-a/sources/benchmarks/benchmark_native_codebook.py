"""Ordinary vLLM text-edit tool calls versus compact generation and learned reuse."""
import argparse
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import sys
import time
import urllib.request
import uuid

from benchmark_codebook_reuse import CASES, ROOT, bridge

TOOL = {'type': 'function', 'function': {
    'name': 'edit', 'description': 'Replace one unique exact text occurrence in a file. Use the smallest sufficient replacement.',
    'parameters': {'type': 'object', 'properties': {
        'path': {'type': 'string'}, 'oldText': {'type': 'string'}, 'newText': {'type': 'string'}},
        'required': ['path', 'oldText', 'newText'], 'additionalProperties': False}}}


def native(b, project, task):
    started = time.perf_counter()
    source = (project / 'app.py').read_text()
    payload = {'model': b.MODEL, 'messages': [
        {'role': 'system', 'content': 'Apply the requested change to app.py using exactly one edit tool call. Preserve unrelated code. Do not explain.'},
        {'role': 'user', 'content': 'SOURCE:\n' + source + '\nTASK:\n' + task}],
        'tools': [TOOL], 'tool_choice': 'auto', 'temperature': 0, 'max_tokens': 2048,
        'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}, 'cache_salt': uuid.uuid4().hex}
    result = {'status': 'error', 'request': payload, 'cache_hit': False,
              'accounting': {'inference_requests': 1, 'usage_complete': False,
                             'known_input_tokens': 0, 'known_generated_argument_tokens': 0,
                             'known_classification_control_records': 0}}
    try:
        headers = {'Content-Type': 'application/json'}
        if os.environ.get('PIJIT_API_KEY'):
            headers['Authorization'] = 'Bearer ' + os.environ['PIJIT_API_KEY']
        request = urllib.request.Request(os.environ['PIJIT_URL'].rstrip('/') + '/v1/chat/completions',
                                         data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=195) as response:
            raw = json.load(response)
        result.update(response=raw, request_id=raw['id'], http_seconds=time.perf_counter() - started)
        usage = raw['usage']
        result['accounting'].update(usage_complete=True, known_input_tokens=usage['prompt_tokens'],
                                     known_generated_argument_tokens=usage['completion_tokens'])
        choice = raw['choices'][0]
        calls = choice['message'].get('tool_calls') or []
        if choice['finish_reason'] not in ('stop', 'tool_calls') or len(calls) != 1:
            raise ValueError('Expected one complete native tool call')
        call = calls[0]['function']
        args = json.loads(call['arguments'])
        if call['name'] != 'edit' or set(args) != {'path', 'oldText', 'newText'} or args['path'] != 'app.py':
            raise ValueError('Unexpected native edit')
        old, new = args['oldText'], args['newText']
        if not isinstance(old, str) or not old or not isinstance(new, str) or source.count(old) != 1:
            raise ValueError('Native edit must match one unique exact source span')
        updated = source.replace(old, new, 1)
        compile(updated, 'app.py', 'exec')
        backup, verification = b.apply_edit(project / 'app.py', source, updated, project, b.paths(project))
        result.update(status='ok', backup=str(backup), validation=verification)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['wall_seconds'] = time.perf_counter() - started
    return result


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['PIJIT_URL'] = args.url
    for key in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_TOKENIZER_REVISION'):
        os.environ.pop(key, None)
    b = bridge(ROOT, 'native_comparison_bridge')
    (out / 'manifest.json').write_text(json.dumps({
        'cases': CASES, 'repeats': args.repeats, 'seed': 919, 'native_tool': TOOL,
        'native': 'ordinary auto tool call, no direct classifier or structured_outputs; same patched server ordinary path, not an unpatched vLLM binary',
        'method': 'edit-only; same source/task/oracle; fresh state per repeat/arm; reset source each case; keep codebook across cases; interleaved arms; no retry; full client wall includes apply and validation; shared backend',
        'tokens': 'native completion_tokens include serialized tool call; TAIR argument tokens and classification controls are separate',
    }, indent=2))
    shutil.copyfile(__file__, out / Path(__file__).name)
    rng = random.Random(919)
    with (out / 'rows.jsonl').open('x') as stream:
        for repeat in range(args.repeats):
            for name, task, source, value, alias in CASES:
                arms = ['native', 'compact_generate', 'optimized']
                rng.shuffle(arms)
                for arm in arms:
                    root = out / f'{repeat}-{arm}'
                    project = root / 'project'
                    project.mkdir(parents=True, exist_ok=True)
                    app = project / 'app.py'
                    app.write_text(source)
                    b.STATE = root / 'state'
                    oracle = root / 'oracle.py'
                    extra = 'assert p.parse_args(["-w", "9"]).workers == 9\n' if alias else ''
                    oracle.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()))\nfrom app import build_parser\np=build_parser()\n' +
                        f'assert p.parse_args([]).workers == {value}\n' +
                        'assert p.parse_args(["--workers", "7"]).workers == 7\nassert len(p._actions) == 2\n' + extra)
                    os.environ['PIJIT_DISABLE_CODEBOOK'] = str(int(arm != 'optimized'))
                    os.environ['PIJIT_VERIFY_CMD'] = shlex.join([sys.executable, '-B', str(oracle)])
                    result = native(b, project, task) if arm == 'native' else b.run({
                        'action': 'edit', 'cwd': str(project), 'path': 'app.py', 'task': task})
                    row = {'repeat': repeat, 'case': name, 'arm': arm, 'correct': result['status'] == 'ok',
                           'result': result, 'after': app.read_text()}
                    stream.write(json.dumps(row) + '\n')
                    stream.flush()
                    book = b.paths(project) / 'codebook.json'
                    if book.exists():
                        shutil.copyfile(book, out / f'{repeat}-{name}-{arm}-book.json')
                    print(repeat, name, arm, row['correct'], round(result['wall_seconds'], 4),
                          result.get('cache_hit'), result.get('error'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--repeats', type=int, default=3)
    main(parser.parse_args())
