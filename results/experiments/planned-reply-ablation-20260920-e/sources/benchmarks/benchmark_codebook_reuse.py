"""Matched generation/legacy/current codebook runs and held-out candidate rejection."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shlex
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "import argparse\ndef build_parser():\n    p = argparse.ArgumentParser()\n    p.add_argument('--workers', type=int, default=4)\n    return p\n"
CASES = [
    ('cold', 'Change --workers default to 6.', SOURCE, 6, False),
    ('repeat', 'Change --workers default to 6.', SOURCE, 6, False),
    ('new_value', 'Change --workers default to 8.', SOURCE, 8, False),
    ('paraphrase', 'Set the default value for --workers to 10.', SOURCE, 10, False),
    ('source_change', 'Change --workers default to 12.', SOURCE + '# unrelated comment\n', 12, False),
    ('alias_cold', 'Add alias -w to --workers.', SOURCE, 4, True),
    ('alias_repeat', 'Add alias -w to --workers.', SOURCE, 4, True),
]
GUARD_SOURCE = SOURCE.replace('    return p', "    p.add_argument('--timeout', type=int, default=3, help='old')\n    return p")
CHALLENGES = [
    ('wrong_value', 'Change --workers default to 8.', [['kw', '--workers', 'default', 9]], False),
    ('wrong_target', 'Change --workers default to 8.', [['kw', '--timeout', 'default', 8]], False),
    ('wrong_property', 'Change --timeout default to 8.', [['kw', '--timeout', 'help', '8']], False),
    ('extra_edit', 'Change --workers default to 8.', [['kw', '--workers', 'default', 8], ['kw', '--timeout', 'default', 8]], False),
    ('wrong_type', 'Change --workers default to 1.', [['kw', '--workers', 'default', True]], False),
    ('negated', 'Do not change --workers default to 8.', [['kw', '--workers', 'default', 8]], False),
    ('compound', 'Change --workers default to 8 and add alias -w.', [['kw', '--workers', 'default', 8]], False),
    ('heldout_integer', 'Update the default value for --timeout to 7.', [['kw', '--timeout', 'default', 7]], True),
    ('heldout_string', 'Change --timeout help to "Wait duration".', [['kw', '--timeout', 'help', 'Wait duration']], True),
]


def bridge(root, name):
    spec = importlib.util.spec_from_file_location(name, root / 'integrations/pijit/bridge.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['PIJIT_URL'] = args.url
    for key in ('PIJIT_SCHEMA_ACTIONS', 'PIJIT_JIT_ACTIONS', 'PIJIT_TOKENIZER_REVISION'):
        os.environ.pop(key, None)
    current = bridge(ROOT, 'current_bridge')
    legacy = bridge(args.legacy_root.resolve(), 'legacy_bridge')
    modules = {'generate': current, 'legacy': legacy, 'optimized': current}
    (out / 'manifest.json').write_text(json.dumps({
        'cases': CASES, 'challenges': CHALLENGES, 'repeats': args.repeats, 'seed': 918,
        'arms': list(modules), 'url': args.url,
        'method': 'fresh state per arm/repeat; reset declared source before each case; retain book; shuffled arm order; no retries; full bridge wall includes oracle; no label cache; edit-only shared backend',
    }, indent=2))
    shutil.copyfile(__file__, out / Path(__file__).name)
    rng = random.Random(918)
    with (out / 'rows.jsonl').open('x') as stream:
        for repeat in range(args.repeats):
            for name, task, source, value, alias in CASES:
                arms = list(modules)
                rng.shuffle(arms)
                for arm in arms:
                    b = modules[arm]
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
                    os.environ['PIJIT_DISABLE_CODEBOOK'] = str(int(arm == 'generate'))
                    os.environ['PIJIT_VERIFY_CMD'] = shlex.join([sys.executable, '-B', str(oracle)])
                    result = b.run({'action': 'edit', 'cwd': str(project), 'path': 'app.py', 'task': task})
                    row = {'repeat': repeat, 'case': name, 'arm': arm, 'correct': result['status'] == 'ok',
                           'result': result, 'after': app.read_text()}
                    stream.write(json.dumps(row) + '\n')
                    stream.flush()
                    book = b.paths(project) / 'codebook.json'
                    if book.exists():
                        shutil.copyfile(book, out / f'{repeat}-{name}-{arm}-book.json')
                    print(repeat, name, arm, row['correct'], round(result['wall_seconds'], 4),
                          result.get('cache_hit'), flush=True)
    with (out / 'challenges.jsonl').open('x') as stream:
        for name, task, edits, expected in CHALLENGES:
            for arm, b in [('legacy', legacy), ('optimized', current)]:
                trace = {'stage_seconds': {}, 'http_requests': []}
                token = b.TRACE.set(trace)
                started = time.perf_counter()
                try:
                    selected, record = b.pick_cached(GUARD_SOURCE, task, [{'id': 0, 'edits': edits}])
                    row = {'case': name, 'arm': arm, 'expected_accept': expected,
                           'accepted': selected is not None, 'correct': (selected is not None) == expected,
                           'record': record, 'trace': trace, 'wall_seconds': time.perf_counter() - started}
                except Exception as error:
                    row = {'case': name, 'arm': arm, 'correct': False, 'error': str(error), 'trace': trace}
                finally:
                    b.TRACE.reset(token)
                stream.write(json.dumps(row) + '\n')
                stream.flush()
                print('challenge', name, arm, row['correct'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--legacy-root', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--repeats', type=int, default=3)
    main(parser.parse_args())
